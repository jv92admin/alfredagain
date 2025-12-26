"""
Alfred Web UI - FastAPI application.

Quick alpha testing UI for sharing with friends.
"""

import asyncio
import json
import secrets
import logging
from datetime import datetime, timedelta
from typing import Any

import bcrypt
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sse_starlette.sse import EventSourceResponse

from alfred.db.client import get_client
from alfred.graph.workflow import run_alfred, run_alfred_streaming
from alfred.memory.conversation import initialize_conversation
from alfred.graph.state import ConversationContext

logger = logging.getLogger(__name__)

# Simple in-memory session store (good enough for alpha)
sessions: dict[str, dict[str, Any]] = {}

app = FastAPI(title="Alfred", version="2.0.0")


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return {"status": "healthy"}


# =============================================================================
# Models
# =============================================================================

class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    message: str
    log_prompts: bool = False


# =============================================================================
# Session Management
# =============================================================================

def get_session(request: Request) -> dict[str, Any] | None:
    """Get session from cookie."""
    session_id = request.cookies.get("alfred_session")
    if not session_id:
        return None
    session = sessions.get(session_id)
    if session and session.get("expires_at", datetime.min) > datetime.now():
        return session
    return None


def require_session(request: Request) -> dict[str, Any]:
    """Require valid session or raise 401."""
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


def create_session(user_id: str, email: str, display_name: str) -> str:
    """Create a new session and return session ID."""
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "conversation": initialize_conversation(),
        "expires_at": datetime.now() + timedelta(days=7),
    }
    return session_id


# =============================================================================
# Auth Endpoints
# =============================================================================

@app.post("/api/login")
async def login(req: LoginRequest, response: Response):
    """Login with email and password."""
    client = get_client()
    
    # Fetch user by email
    result = client.table("users").select("id, email, password_hash, display_name").eq("email", req.email).execute()
    
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user = result.data[0]
    password_hash = user.get("password_hash")
    
    if not password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check password
    if not bcrypt.checkpw(req.password.encode(), password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create session
    session_id = create_session(
        user_id=user["id"],
        email=user["email"],
        display_name=user.get("display_name") or user["email"].split("@")[0],
    )
    
    response.set_cookie(
        key="alfred_session",
        value=session_id,
        httponly=True,
        max_age=60 * 60 * 24 * 7,  # 7 days
        samesite="lax",
    )
    
    return {"success": True, "display_name": user.get("display_name") or user["email"]}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    """Logout and clear session."""
    session_id = request.cookies.get("alfred_session")
    if session_id and session_id in sessions:
        del sessions[session_id]
    response.delete_cookie("alfred_session")
    return {"success": True}


@app.get("/api/me")
async def get_me(session: dict = Depends(require_session)):
    """Get current user info."""
    return {
        "user_id": session["user_id"],
        "email": session["email"],
        "display_name": session["display_name"],
    }


# =============================================================================
# Chat Endpoint
# =============================================================================

@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request, session: dict = Depends(require_session)):
    """Send a message to Alfred."""
    from alfred.llm.prompt_logger import enable_prompt_logging, get_session_log_dir
    
    try:
        # Enable prompt logging based on user preference
        enable_prompt_logging(req.log_prompts)
        
        # Get conversation from session
        conversation = session.get("conversation") or initialize_conversation()
        
        # Run Alfred
        response_text, updated_conversation = await run_alfred(
            user_message=req.message,
            user_id=session["user_id"],
            conversation=conversation,
        )
        
        # Update session with new conversation state
        session["conversation"] = updated_conversation
        
        # Get log directory
        log_dir = get_session_log_dir()
        
        return {
            "response": response_text,
            "conversation_turns": len(updated_conversation.get("recent_turns", [])),
            "log_dir": str(log_dir) if log_dir else None,
        }
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/reset")
async def reset_chat(session: dict = Depends(require_session)):
    """Reset conversation history."""
    session["conversation"] = initialize_conversation()
    return {"success": True}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request, session: dict = Depends(require_session)):
    """Send a message to Alfred with streaming progress updates."""
    from alfred.llm.prompt_logger import enable_prompt_logging, get_session_log_dir
    
    async def event_generator():
        try:
            # Enable prompt logging based on user preference
            enable_prompt_logging(req.log_prompts)
            
            # Get conversation from session
            conversation = session.get("conversation") or initialize_conversation()
            
            # Stream Alfred's progress
            async for update in run_alfred_streaming(
                user_message=req.message,
                user_id=session["user_id"],
                conversation=conversation,
            ):
                if update["type"] == "done":
                    # Update session with new conversation state
                    session["conversation"] = update["conversation"]
                    # Get log directory
                    log_dir = get_session_log_dir()
                    yield {
                        "event": "done",
                        "data": json.dumps({
                            "response": update["response"],
                            "log_dir": str(log_dir) if log_dir else None,
                        }),
                    }
                else:
                    yield {
                        "event": "progress",
                        "data": json.dumps(update),
                    }
        except Exception as e:
            logger.exception("Stream chat error")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
    
    return EventSourceResponse(event_generator())


# =============================================================================
# Data Endpoints
# =============================================================================

@app.get("/api/tables/inventory")
async def get_inventory(session: dict = Depends(require_session)):
    """Get user's inventory."""
    client = get_client()
    result = client.table("inventory").select("*").eq("user_id", session["user_id"]).order("name").execute()
    return {"data": result.data}


@app.get("/api/tables/recipes")
async def get_recipes(session: dict = Depends(require_session)):
    """Get user's recipes."""
    client = get_client()
    result = client.table("recipes").select("*").eq("user_id", session["user_id"]).order("created_at", desc=True).execute()
    return {"data": result.data}


@app.get("/api/tables/recipes/{recipe_id}/ingredients")
async def get_recipe_ingredients(recipe_id: str, session: dict = Depends(require_session)):
    """Get ingredients for a specific recipe."""
    client = get_client()
    # First verify the recipe belongs to user
    recipe = client.table("recipes").select("id").eq("id", recipe_id).eq("user_id", session["user_id"]).execute()
    if not recipe.data:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    result = client.table("recipe_ingredients").select("*").eq("recipe_id", recipe_id).execute()
    return {"data": result.data}


@app.get("/api/tables/shopping")
async def get_shopping_list(session: dict = Depends(require_session)):
    """Get user's shopping list."""
    client = get_client()
    result = client.table("shopping_list").select("*").eq("user_id", session["user_id"]).order("name").execute()
    return {"data": result.data}


@app.get("/api/tables/meal_plans")
async def get_meal_plans(session: dict = Depends(require_session)):
    """Get user's meal plans."""
    client = get_client()
    result = client.table("meal_plans").select("*").eq("user_id", session["user_id"]).order("date", desc=True).execute()
    return {"data": result.data}


@app.get("/api/tables/tasks")
async def get_tasks(session: dict = Depends(require_session)):
    """Get user's tasks."""
    client = get_client()
    result = client.table("tasks").select("*").eq("user_id", session["user_id"]).order("due_date").execute()
    return {"data": result.data}


@app.get("/api/tables/cooking_log")
async def get_cooking_log(session: dict = Depends(require_session)):
    """Get user's cooking history."""
    client = get_client()
    result = client.table("cooking_log").select("*").eq("user_id", session["user_id"]).order("cooked_at", desc=True).execute()
    return {"data": result.data}


@app.get("/api/tables/preferences")
async def get_preferences(session: dict = Depends(require_session)):
    """Get user's preferences."""
    client = get_client()
    result = client.table("preferences").select("*").eq("user_id", session["user_id"]).execute()
    return {"data": result.data}


# =============================================================================
# Frontend
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main page."""
    return get_frontend_html()


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve the login page."""
    return get_login_html()


def get_login_html() -> str:
    """Return login page HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alfred - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e8e8e8;
        }
        
        .login-container {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 48px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.3);
        }
        
        .logo {
            text-align: center;
            margin-bottom: 32px;
        }
        
        .logo h1 {
            font-size: 2.5rem;
            font-weight: 300;
            letter-spacing: 4px;
            color: #f39c12;
        }
        
        .logo p {
            color: #888;
            margin-top: 8px;
            font-size: 0.9rem;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-size: 0.9rem;
            color: #aaa;
        }
        
        input {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            font-size: 1rem;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        
        input:focus {
            outline: none;
            border-color: #f39c12;
            box-shadow: 0 0 0 3px rgba(243, 156, 18, 0.2);
        }
        
        input::placeholder {
            color: #666;
        }
        
        button {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 8px;
            background: linear-gradient(135deg, #f39c12, #e67e22);
            color: #fff;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(243, 156, 18, 0.3);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .error {
            background: rgba(231, 76, 60, 0.2);
            border: 1px solid rgba(231, 76, 60, 0.5);
            color: #e74c3c;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.9rem;
            display: none;
        }
        
        .test-users {
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            font-size: 0.85rem;
            color: #666;
        }
        
        .test-users strong {
            color: #888;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <h1>ALFRED</h1>
            <p>Your Kitchen Assistant</p>
        </div>
        
        <div class="error" id="error"></div>
        
        <form id="loginForm">
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" placeholder="alice@test.local" required>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" placeholder="Enter password" required>
            </div>
            
            <button type="submit" id="submitBtn">Sign In</button>
        </form>
        
        <div class="test-users">
            <strong>Test accounts:</strong><br>
            alice@test.local<br>
            bob@test.local<br>
            carol@test.local
        </div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const error = document.getElementById('error');
            
            btn.disabled = true;
            btn.textContent = 'Signing in...';
            error.style.display = 'none';
            
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: document.getElementById('email').value,
                        password: document.getElementById('password').value,
                    }),
                });
                
                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || 'Login failed');
                }
                
                window.location.href = '/';
            } catch (err) {
                error.textContent = err.message;
                error.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.textContent = 'Sign In';
            }
        });
    </script>
</body>
</html>'''


def get_frontend_html() -> str:
    """Return main app HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alfred</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-dark: #0d1117;
            --bg-card: #161b22;
            --bg-input: #0d1117;
            --border: #30363d;
            --text: #e6edf3;
            --text-muted: #8b949e;
            --accent: #f39c12;
            --accent-hover: #e67e22;
            --success: #3fb950;
            --danger: #f85149;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            min-height: 100vh;
        }
        
        /* Header */
        header {
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: 300;
            letter-spacing: 3px;
            color: var(--accent);
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .user-name {
            color: var(--text-muted);
        }
        
        .logout-btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        
        .logout-btn:hover {
            border-color: var(--danger);
            color: var(--danger);
        }
        
        /* Main Layout */
        .main-container {
            display: grid;
            grid-template-columns: 1fr 400px;
            height: calc(100vh - 65px);
        }
        
        /* Data Panel */
        .data-panel {
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
        }
        
        .tabs {
            display: flex;
            border-bottom: 1px solid var(--border);
            background: var(--bg-card);
        }
        
        .tab {
            padding: 14px 24px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 0.95rem;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        
        .tab:hover {
            color: var(--text);
            background: rgba(255, 255, 255, 0.03);
        }
        
        .tab.active {
            color: var(--accent);
            border-bottom-color: var(--accent);
        }
        
        .data-content {
            flex: 1;
            overflow: auto;
            padding: 20px;
        }
        
        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }
        
        th {
            text-align: left;
            padding: 12px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            color: var(--text-muted);
            font-weight: 500;
            position: sticky;
            top: 0;
        }
        
        td {
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }
        
        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }
        
        .empty-state {
            text-align: center;
            padding: 48px;
            color: var(--text-muted);
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            background: rgba(243, 156, 18, 0.2);
            color: var(--accent);
        }
        
        .badge.green {
            background: rgba(63, 185, 80, 0.2);
            color: var(--success);
        }
        
        /* Chat Panel */
        .chat-panel {
            display: flex;
            flex-direction: column;
            background: var(--bg-card);
        }
        
        .chat-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .chat-header h2 {
            font-size: 1.1rem;
            font-weight: 500;
        }
        
        .reset-btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8rem;
        }
        
        .reset-btn:hover {
            border-color: var(--accent);
            color: var(--accent);
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        
        .message {
            margin-bottom: 16px;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.user {
            text-align: right;
        }
        
        .message-bubble {
            display: inline-block;
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 12px;
            text-align: left;
        }
        
        .message.user .message-bubble {
            background: var(--accent);
            color: #000;
            border-bottom-right-radius: 4px;
        }
        
        .message.assistant .message-bubble {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }
        
        .message-sender {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        
        .chat-input-container {
            padding: 12px 20px 16px;
            border-top: 1px solid var(--border);
            flex-shrink: 0;
        }
        
        .chat-input-wrapper {
            display: flex;
            gap: 12px;
        }
        
        #chatInput {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg-input);
            color: var(--text);
            font-size: 0.95rem;
            resize: none;
        }
        
        #chatInput:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        #sendBtn {
            padding: 12px 24px;
            background: var(--accent);
            border: none;
            border-radius: 8px;
            color: #000;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        #sendBtn:hover:not(:disabled) {
            background: var(--accent-hover);
        }
        
        #sendBtn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .chat-options {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
            font-size: 0.85rem;
            padding: 8px 0;
        }
        
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-muted);
            cursor: pointer;
            padding: 4px 8px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
        }
        
        .checkbox-label:hover {
            border-color: var(--accent);
            color: var(--text);
        }
        
        .checkbox-label input {
            accent-color: var(--accent);
            width: 16px;
            height: 16px;
            cursor: pointer;
        }
        
        .log-dir {
            color: var(--accent);
            font-family: monospace;
            font-size: 0.75rem;
        }
        
        .typing-indicator {
            display: none;
            padding: 12px 16px;
            color: var(--text-muted);
            font-style: italic;
        }
        
        .typing-indicator.visible {
            display: block;
        }
        
        .progress-trail {
            display: flex;
            flex-direction: column;
            gap: 6px;
            font-size: 0.85rem;
        }
        
        .progress-step {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-muted);
        }
        
        .progress-step.completed {
            color: var(--success);
        }
        
        .progress-step.active {
            color: var(--accent);
            font-weight: 500;
        }
        
        .progress-step.pending {
            opacity: 0.5;
        }
        
        .step-icon {
            width: 16px;
            text-align: center;
        }
        
        /* Loading */
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }
        
        .spinner {
            width: 24px;
            height: 24px;
            border: 2px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 12px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Responsive */
        @media (max-width: 900px) {
            .main-container {
                grid-template-columns: 1fr;
                grid-template-rows: 1fr 1fr;
            }
            
            .data-panel {
                border-right: none;
                border-bottom: 1px solid var(--border);
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="logo">ALFRED</div>
        <div class="user-info">
            <span class="user-name" id="userName">Loading...</span>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
    </header>
    
    <div class="main-container">
        <div class="data-panel">
            <div class="tabs">
                <button class="tab active" data-tab="inventory">Inventory</button>
                <button class="tab" data-tab="recipes">Recipes</button>
                <button class="tab" data-tab="shopping">Shopping</button>
                <button class="tab" data-tab="meal_plans">Meal Plan</button>
                <button class="tab" data-tab="tasks">Tasks</button>
                <button class="tab" data-tab="cooking_log">History</button>
                <button class="tab" data-tab="preferences">Preferences</button>
            </div>
            <div class="data-content" id="dataContent">
                <div class="loading">
                    <div class="spinner"></div>
                    Loading...
                </div>
            </div>
        </div>
        
        <div class="chat-panel">
            <div class="chat-header">
                <h2>Chat with Alfred</h2>
                <button class="reset-btn" onclick="resetChat()">Reset</button>
            </div>
            <div class="chat-messages" id="chatMessages">
                <div class="message assistant">
                    <div class="message-sender">Alfred</div>
                    <div class="message-bubble">
                        Hello! I'm Alfred, your kitchen assistant. I can help you manage your pantry, find recipes, create shopping lists, and plan meals. What would you like to do?
                    </div>
                </div>
            </div>
            <div class="typing-indicator" id="typingIndicator">Alfred is thinking...</div>
            <div class="chat-input-container">
                <div class="chat-options">
                    <label class="checkbox-label">
                        <input type="checkbox" id="logPrompts" checked> 📝 Log prompts
                    </label>
                    <span id="logDir" class="log-dir"></span>
                </div>
                <div class="chat-input-wrapper">
                    <textarea id="chatInput" rows="1" placeholder="Ask Alfred anything..." onkeydown="handleKeydown(event)"></textarea>
                    <button id="sendBtn" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentTab = 'inventory';
        
        // Check auth on load
        async function checkAuth() {
            try {
                const res = await fetch('/api/me');
                if (!res.ok) throw new Error('Not authenticated');
                const data = await res.json();
                document.getElementById('userName').textContent = data.display_name;
                loadData(currentTab);
            } catch {
                window.location.href = '/login';
            }
        }
        
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTab = tab.dataset.tab;
                loadData(currentTab);
            });
        });
        
        // Load data for tab
        async function loadData(tab) {
            const content = document.getElementById('dataContent');
            content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
            
            try {
                const res = await fetch(`/api/tables/${tab}`);
                const { data } = await res.json();
                content.innerHTML = renderTable(tab, data);
            } catch (err) {
                content.innerHTML = `<div class="empty-state">Error loading data</div>`;
            }
        }
        
        // Render table based on type
        function renderTable(type, data) {
            if (!data || data.length === 0) {
                return `<div class="empty-state">No ${type} items yet. Chat with Alfred to add some!</div>`;
            }
            
            switch(type) {
                case 'inventory':
                    return `<table>
                        <thead><tr><th>Item</th><th>Quantity</th><th>Location</th><th>Expiry</th></tr></thead>
                        <tbody>${data.map(item => `<tr>
                            <td>${item.name}</td>
                            <td>${item.quantity} ${item.unit || ''}</td>
                            <td>${item.location || '-'}</td>
                            <td>${item.expiry_date || '-'}</td>
                        </tr>`).join('')}</tbody>
                    </table>`;
                    
                case 'recipes':
                    return `<table>
                        <thead><tr><th>Recipe</th><th>Cuisine</th><th>Time</th><th>Difficulty</th></tr></thead>
                        <tbody>${data.map(r => `<tr>
                            <td>${r.name}</td>
                            <td>${r.cuisine || '-'}</td>
                            <td>${(r.prep_time_minutes || 0) + (r.cook_time_minutes || 0)} min</td>
                            <td><span class="badge">${r.difficulty || 'easy'}</span></td>
                        </tr>`).join('')}</tbody>
                    </table>`;
                    
                case 'shopping':
                    return `<table>
                        <thead><tr><th>Item</th><th>Quantity</th><th>Category</th><th>Status</th></tr></thead>
                        <tbody>${data.map(item => `<tr>
                            <td>${item.name}</td>
                            <td>${item.quantity ? `${item.quantity} ${item.unit || ''}` : '-'}</td>
                            <td>${item.category || '-'}</td>
                            <td><span class="badge ${item.is_purchased ? 'green' : ''}">${item.is_purchased ? 'Purchased' : 'Pending'}</span></td>
                        </tr>`).join('')}</tbody>
                    </table>`;
                    
                case 'meal_plans':
                    return `<table>
                        <thead><tr><th>Date</th><th>Meal</th><th>Notes</th><th>Servings</th></tr></thead>
                        <tbody>${data.map(m => `<tr>
                            <td>${m.date}</td>
                            <td><span class="badge">${m.meal_type}</span></td>
                            <td>${m.notes || '-'}</td>
                            <td>${m.servings || 1}</td>
                        </tr>`).join('')}</tbody>
                    </table>`;
                    
                case 'tasks':
                    return `<table>
                        <thead><tr><th>Task</th><th>Due</th><th>Category</th><th>Status</th></tr></thead>
                        <tbody>${data.map(t => `<tr>
                            <td>${t.title}</td>
                            <td>${t.due_date || '-'}</td>
                            <td><span class="badge">${t.category || 'other'}</span></td>
                            <td><span class="badge ${t.completed ? 'green' : ''}">${t.completed ? 'Done' : 'Pending'}</span></td>
                        </tr>`).join('')}</tbody>
                    </table>`;
                    
                case 'cooking_log':
                    return `<table>
                        <thead><tr><th>Date</th><th>Recipe</th><th>Rating</th><th>Notes</th></tr></thead>
                        <tbody>${data.map(l => `<tr>
                            <td>${new Date(l.cooked_at).toLocaleDateString()}</td>
                            <td>${l.recipe_id ? '(Recipe)' : '-'}</td>
                            <td>${l.rating ? '★'.repeat(l.rating) + '☆'.repeat(5 - l.rating) : '-'}</td>
                            <td>${l.notes || '-'}</td>
                        </tr>`).join('')}</tbody>
                    </table>`;
                    
                case 'preferences':
                    if (data.length === 0) return `<div class="empty-state">No preferences set yet. Chat with Alfred to set them!</div>`;
                    const p = data[0];
                    return `<table>
                        <tbody>
                            <tr><td><strong>Household Size</strong></td><td>${p.household_size || '-'}</td></tr>
                            <tr><td><strong>Dietary Restrictions</strong></td><td>${p.dietary_restrictions || '-'}</td></tr>
                            <tr><td><strong>Allergies</strong></td><td>${(p.allergies || []).join(', ') || '-'}</td></tr>
                            <tr><td><strong>Cuisine Preferences</strong></td><td>${(p.cuisine_preferences || []).join(', ') || '-'}</td></tr>
                            <tr><td><strong>Skill Level</strong></td><td>${p.skill_level || '-'}</td></tr>
                            <tr><td><strong>Nutrition Goals</strong></td><td>${(p.nutrition_goals || []).join(', ') || '-'}</td></tr>
                            <tr><td><strong>Cooking Frequency</strong></td><td>${p.cooking_frequency || '-'}</td></tr>
                            <tr><td><strong>Equipment</strong></td><td>${(p.available_equipment || []).join(', ') || '-'}</td></tr>
                            <tr><td><strong>Time Budget</strong></td><td>${p.time_budget_minutes ? p.time_budget_minutes + ' min' : '-'}</td></tr>
                        </tbody>
                    </table>`;
                    
                default:
                    return `<div class="empty-state">Unknown tab</div>`;
            }
        }
        
        // Chat functions
        function addMessage(sender, text) {
            const messages = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.className = `message ${sender}`;
            div.innerHTML = `
                <div class="message-sender">${sender === 'user' ? 'You' : 'Alfred'}</div>
                <div class="message-bubble">${text}</div>
            `;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }
        
        // Progress state
        let progressState = {
            steps: [],
            currentStep: 0,
            planComplete: false
        };
        
        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const btn = document.getElementById('sendBtn');
            const typing = document.getElementById('typingIndicator');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Reset progress state
            progressState = { steps: [], currentStep: 0, planComplete: false };
            
            addMessage('user', message);
            input.value = '';
            btn.disabled = true;
            typing.classList.add('visible');
            typing.innerHTML = '<div class="progress-trail"><div class="progress-step active"><span class="step-icon">◐</span> Planning...</div></div>';
            
            try {
                const logPrompts = document.getElementById('logPrompts').checked;
                
                // Use streaming endpoint
                const res = await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message, log_prompts: logPrompts }),
                });
                
                if (!res.ok) throw new Error('Chat failed');
                
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let currentEvent = 'progress';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    buffer = lines.pop();
                    
                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            currentEvent = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (currentEvent === 'done') {
                                    // Final response
                                    addMessage('assistant', data.response);
                                    if (data.log_dir) {
                                        document.getElementById('logDir').textContent = 'Logs: ' + data.log_dir;
                                    }
                                } else if (currentEvent === 'error') {
                                    addMessage('assistant', 'Error: ' + data.error);
                                } else {
                                    handleStreamEvent(data);
                                }
                            } catch {}
                        }
                    }
                }
                
                // Refresh current data tab
                loadData(currentTab);
            } catch (err) {
                addMessage('assistant', 'Sorry, something went wrong. Please try again.');
            } finally {
                btn.disabled = false;
                typing.classList.remove('visible');
            }
        }
        
        function handleStreamEvent(data) {
            const typing = document.getElementById('typingIndicator');
            
            switch (data.type) {
                case 'thinking':
                    typing.innerHTML = '<div class="progress-trail"><div class="progress-step active"><span class="step-icon">◐</span> Planning...</div></div>';
                    break;
                case 'plan':
                    progressState.steps = data.steps || [];
                    progressState.planComplete = true;
                    renderProgress();
                    break;
                case 'step':
                    progressState.currentStep = data.step;
                    renderProgress();
                    break;
                case 'step_complete':
                    // Mark current step as complete
                    renderProgress(data.step);
                    break;
                case 'working':
                    // Act loop within same step - add dots
                    progressState.workingDots = (progressState.workingDots || 0) + 1;
                    if (progressState.workingDots > 3) progressState.workingDots = 1;
                    renderProgress(null, progressState.workingDots);
                    break;
            }
        }
        
        function renderProgress(completedStep, workingDots = 0) {
            const typing = document.getElementById('typingIndicator');
            let html = '<div class="progress-trail">';
            
            // Planning row
            html += `<div class="progress-step completed"><span class="step-icon">✓</span> Planned ${progressState.steps.length} steps</div>`;
            
            // Step rows
            for (let i = 0; i < progressState.steps.length; i++) {
                const stepNum = i + 1;
                const desc = progressState.steps[i];
                let status = 'pending';
                let icon = '○';
                
                if (completedStep && stepNum <= completedStep) {
                    status = 'completed';
                    icon = '✓';
                } else if (stepNum === progressState.currentStep) {
                    status = 'active';
                    icon = '◐';
                }
                
                // Add working dots for active step
                const dots = (status === 'active' && workingDots > 0) ? '.'.repeat(workingDots) : '';
                html += `<div class="progress-step ${status}"><span class="step-icon">${icon}</span> Step ${stepNum}: ${desc}${dots}</div>`;
            }
            
            html += '</div>';
            typing.innerHTML = html;
        }
        
        function handleKeydown(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }
        
        async function resetChat() {
            if (!confirm('Reset conversation history?')) return;
            
            try {
                await fetch('/api/chat/reset', { method: 'POST' });
                document.getElementById('chatMessages').innerHTML = `
                    <div class="message assistant">
                        <div class="message-sender">Alfred</div>
                        <div class="message-bubble">
                            Hello! I'm Alfred, your kitchen assistant. I can help you manage your pantry, find recipes, create shopping lists, and plan meals. What would you like to do?
                        </div>
                    </div>
                `;
            } catch {
                alert('Failed to reset chat');
            }
        }
        
        async function logout() {
            await fetch('/api/logout', { method: 'POST' });
            window.location.href = '/login';
        }
        
        // Init
        checkAuth();
    </script>
</body>
</html>'''


def create_app() -> FastAPI:
    """Create and return the FastAPI application."""
    return app

