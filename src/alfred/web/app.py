"""
Alfred Web UI - FastAPI application.

Quick alpha testing UI for sharing with friends.
"""

import asyncio
import json
import secrets
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import bcrypt
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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

# CORS middleware for React frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    mode: str = "plan"  # V3: "quick" | "plan"


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
            mode=req.mode,  # V3: Pass mode
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
                mode=req.mode,  # V3: Pass mode
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
# Mutations (PATCH/DELETE) for inline editing
# =============================================================================

class ShoppingItemUpdate(BaseModel):
    is_purchased: bool | None = None
    quantity: float | None = None
    name: str | None = None

class TaskUpdate(BaseModel):
    completed: bool | None = None
    title: str | None = None
    due_date: str | None = None

class InventoryUpdate(BaseModel):
    quantity: float | None = None
    name: str | None = None
    location: str | None = None
    expiry_date: str | None = None

class MealPlanUpdate(BaseModel):
    recipe_id: str | None = None
    notes: str | None = None
    servings: int | None = None
    meal_type: str | None = None

@app.patch("/api/tables/shopping_list/{item_id}")
async def update_shopping_item(item_id: str, update: ShoppingItemUpdate, session: dict = Depends(require_session)):
    """Update a shopping list item."""
    client = get_client()
    
    # Build update dict with only provided fields
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Verify ownership and update
    result = client.table("shopping_list").update(update_data).eq("id", item_id).eq("user_id", session["user_id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"data": result.data[0]}

@app.patch("/api/tables/tasks/{task_id}")
async def update_task(task_id: str, update: TaskUpdate, session: dict = Depends(require_session)):
    """Update a task."""
    client = get_client()
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = client.table("tasks").update(update_data).eq("id", task_id).eq("user_id", session["user_id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"data": result.data[0]}

@app.patch("/api/tables/inventory/{item_id}")
async def update_inventory_item(item_id: str, update: InventoryUpdate, session: dict = Depends(require_session)):
    """Update an inventory item."""
    client = get_client()
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = client.table("inventory").update(update_data).eq("id", item_id).eq("user_id", session["user_id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"data": result.data[0]}

@app.patch("/api/tables/meal_plans/{meal_plan_id}")
async def update_meal_plan(meal_plan_id: str, update: MealPlanUpdate, session: dict = Depends(require_session)):
    """Update a meal plan."""
    client = get_client()
    
    # Handle recipe_id specially - allow explicit null to unassign
    update_data = {}
    for k, v in update.model_dump().items():
        if k == 'recipe_id':
            # Always include recipe_id if it was in the request (even if null)
            if v is not None or 'recipe_id' in update.model_dump(exclude_unset=True):
                update_data[k] = v
        elif v is not None:
            update_data[k] = v
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = client.table("meal_plans").update(update_data).eq("id", meal_plan_id).eq("user_id", session["user_id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    
    return {"data": result.data[0]}

@app.delete("/api/tables/{table}/{item_id}")
async def delete_item(table: str, item_id: str, session: dict = Depends(require_session)):
    """Delete an item from a table."""
    # Whitelist allowed tables
    allowed_tables = {"inventory", "shopping_list", "tasks", "recipes", "meal_plans"}
    if table not in allowed_tables:
        raise HTTPException(status_code=400, detail=f"Table {table} not allowed")
    
    client = get_client()
    result = client.table(table).delete().eq("id", item_id).eq("user_id", session["user_id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"success": True}


# =============================================================================
# Frontend - React SPA
# =============================================================================

# React build location - try multiple paths for dev vs Docker
def find_frontend_dir() -> Path | None:
    """Find the React build directory in dev or Docker."""
    candidates = [
        # Dev: relative to source file
        Path(__file__).parent.parent.parent.parent / "frontend" / "dist",
        # Docker: /app/frontend/dist (pip install puts code in site-packages)
        Path("/app/frontend/dist"),
        # Alt: current working directory
        Path.cwd() / "frontend" / "dist",
    ]
    for path in candidates:
        if path.exists() and (path / "index.html").exists():
            return path
    return None

FRONTEND_DIR = find_frontend_dir()

# Check if build exists
if FRONTEND_DIR is not None:
    # Mount static assets from React build
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA - all routes return index.html, React Router handles routing."""
        # API routes are already handled above, this catches everything else
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        
        # Serve static files if they exist
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
        # Otherwise serve index.html for SPA routing
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    # No React build - show helpful message
    @app.get("/", response_class=HTMLResponse)
    async def no_frontend():
        """Show message when React build is missing."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Alfred - Build Required</title></head>
        <body style="font-family: system-ui; padding: 40px; background: #0d1117; color: #e6edf3;">
            <h1 style="color: #f39c12;">Alfred</h1>
            <p>React frontend not built. Run:</p>
            <pre style="background: #161b22; padding: 16px; border-radius: 8px;">
cd frontend
npm install
npm run build</pre>
            <p>Then restart the server.</p>
        </body>
        </html>
        """



def create_app() -> FastAPI:
    """Create and return the FastAPI application."""
    return app

