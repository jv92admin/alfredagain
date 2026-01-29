"""
Alfred Web UI - FastAPI application.

Uses Supabase Auth with Google OAuth for authentication.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client

from sse_starlette.sse import EventSourceResponse

from alfred.db.client import get_service_client, get_authenticated_client
from alfred.db.request_context import set_request_context, clear_request_context
from alfred.graph.workflow import run_alfred, run_alfred_streaming
from alfred.memory.conversation import initialize_conversation
from alfred.graph.state import ConversationContext
from alfred.config import settings
from alfred.web.session import (
    get_session_status,
    _ensure_metadata,
    create_fresh_session,
    is_session_expired,
    load_conversation_from_db,
    commit_conversation,
    delete_conversation_from_db,
)
from alfred.web.jobs import (
    create_job,
    start_job,
    complete_job,
    fail_job,
    acknowledge_job,
    get_job,
    get_active_job,
)

# Onboarding module (isolated from Alfred's graph)
# Optional import - may not be available in all deployment environments
try:
    from onboarding.api import router as onboarding_router
    ONBOARDING_AVAILABLE = True
except ImportError:
    onboarding_router = None
    ONBOARDING_AVAILABLE = False

# Schema-driven UI routes
from alfred.web.auth import AuthenticatedUser, get_current_user
from alfred.web.schema_routes import router as schema_router
from alfred.web.entity_routes import router as entity_router
from alfred.web.context_routes import router as context_router
from alfred.web.recipe_import_routes import router as recipe_import_router

logger = logging.getLogger(__name__)

# In-memory conversation store (keyed by user_id)
# Note: In production, consider using Redis or database for persistence
conversations: dict[str, dict[str, Any]] = {}

app = FastAPI(title="Alfred", version="2.0.0")


@app.on_event("startup")
async def startup_event():
    """Log configuration on startup."""
    from alfred.llm.prompt_logger import get_logging_status
    status = get_logging_status()
    logger.info(f"Alfred starting up...")
    logger.info(f"  Prompt file logging: {status['file_logging']} (ALFRED_LOG_PROMPTS={status['env_ALFRED_LOG_PROMPTS']})")
    logger.info(f"  Prompt DB logging: {status['db_logging']} (ALFRED_LOG_TO_DB={status['env_ALFRED_LOG_TO_DB']})")


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

# Register onboarding router (separate UI flow from main chat)
if ONBOARDING_AVAILABLE:
    app.include_router(onboarding_router, prefix="/api")

# Register schema-driven UI routes
app.include_router(schema_router, prefix="/api")
app.include_router(entity_router, prefix="/api")
app.include_router(context_router, prefix="/api")
app.include_router(recipe_import_router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return {"status": "healthy"}


# =============================================================================
# Models
# =============================================================================

class UIChange(BaseModel):
    action: str  # "created:user" | "updated:user" | "deleted:user"
    entity_type: str
    id: str  # UUID
    label: str
    data: dict | None = None  # Fresh entity data for creates/updates


class ChatRequest(BaseModel):
    message: str
    log_prompts: bool = False
    mode: str = "plan"  # V3: "quick" | "plan"
    ui_changes: list[UIChange] | None = None  # Phase 3: UI CRUD tracking


# =============================================================================
# Auth - Supabase JWT Validation (see alfred.web.auth)
# =============================================================================

# AuthenticatedUser and get_current_user imported from alfred.web.auth


def get_user_conversation(user_id: str, access_token: str | None = None) -> dict[str, Any]:
    """Get or create conversation state for a user.

    Uses memory cache first, falls back to database, creates fresh if neither exists.
    Handles session expiration and ensures metadata is present.

    Args:
        user_id: User's UUID
        access_token: User's JWT for DB access (optional for backward compat)
    """
    # 1. Check memory cache
    if user_id in conversations:
        conv = conversations[user_id]
        if not is_session_expired(conv):
            _ensure_metadata(conv)
            return conv
        # Expired in cache - try DB before creating fresh

    # 2. Try loading from database
    if access_token:
        conv = load_conversation_from_db(access_token, user_id)
        if conv and not is_session_expired(conv):
            conversations[user_id] = conv  # Cache it
            return conv

    # 3. Create fresh session
    conv = create_fresh_session()
    conversations[user_id] = conv
    return conv


# =============================================================================
# Auth Endpoints
# =============================================================================

@app.get("/api/me")
async def get_me(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user info."""
    # Fetch display name from public.users table
    client = get_authenticated_client(user.access_token)
    result = client.table("users").select("display_name").eq("id", user.id).maybe_single().execute()
    
    display_name = None
    if result.data:
        display_name = result.data.get("display_name")
    
    # Fallback to email prefix if no display name
    if not display_name and user.email:
        display_name = user.email.split("@")[0]
    
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": display_name or "User",
    }


# =============================================================================
# Chat Endpoint
# =============================================================================

@app.post("/api/chat")
async def chat(req: ChatRequest, user: AuthenticatedUser = Depends(get_current_user)):
    """Send a message to Alfred."""
    from alfred.llm.prompt_logger import enable_prompt_logging, set_user_id, get_session_log_dir

    # Convert ui_changes to dict format for workflow
    ui_changes_data = None
    if req.ui_changes:
        ui_changes_data = [c.model_dump() for c in req.ui_changes]

    # Create and start job
    job_id = create_job(user.access_token, user.id, {
        "message": req.message,
        "mode": req.mode,
        "ui_changes": ui_changes_data,
    })
    if job_id:
        start_job(user.access_token, job_id)

    try:
        # Enable prompt logging based on user preference
        enable_prompt_logging(req.log_prompts)

        # Set user ID for logging context
        set_user_id(user.id)

        # Set request context for authenticated DB access
        set_request_context(access_token=user.access_token, user_id=user.id)

        # Get conversation from user's session (with DB fallback)
        conversation = get_user_conversation(user.id, user.access_token)

        # Run Alfred (will use authenticated client via request context)
        response_text, updated_conversation = await run_alfred(
            user_message=req.message,
            user_id=user.id,
            conversation=conversation,
            mode=req.mode,
            ui_changes=ui_changes_data,
        )

        # Get log directory
        log_dir = get_session_log_dir()

        # Complete job first, then commit conversation
        if job_id:
            try:
                complete_job(user.access_token, job_id, {
                    "response": response_text,
                    "log_dir": str(log_dir) if log_dir else None,
                })
            except Exception as e:
                logger.error(f"Failed to complete job {job_id}: {e}")

        # Single commit: stamp metadata + cache + persist to DB
        commit_conversation(user.id, user.access_token, updated_conversation, conversations)

        return {
            "response": response_text,
            "conversation_turns": len(updated_conversation.get("recent_turns", [])),
            "log_dir": str(log_dir) if log_dir else None,
            "job_id": job_id,
        }
    except Exception as e:
        logger.exception("Chat error")
        if job_id:
            fail_job(user.access_token, job_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clear request context
        clear_request_context()


@app.post("/api/chat/reset")
async def reset_chat(user: AuthenticatedUser = Depends(get_current_user)):
    """Reset conversation history and prompt logging session."""
    from alfred.llm.prompt_logger import reset_session

    # Clear from memory
    conversations[user.id] = create_fresh_session()

    # Clear from database
    delete_conversation_from_db(user.access_token, user.id)

    # Start fresh prompt log session
    reset_session()

    return {"success": True}


@app.get("/api/conversation/status")
async def get_conversation_status(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current session status for resume prompt logic.

    Returns:
        - status: "none" | "active" | "stale"
        - last_active_at: ISO timestamp or null
        - preview: {last_message, message_count} or null

    Note: Does NOT delete expired sessions. Cleanup happens on next chat request.
    This prevents the race condition where status returns "none" but chat still has context.
    """
    # 1. Check memory cache
    conv = conversations.get(user.id)

    # 2. If not in cache, try loading from database
    if not conv:
        conv = load_conversation_from_db(user.access_token, user.id)
        if conv:
            conversations[user.id] = conv  # Cache it

    # Return status without deleting (non-destructive check)
    # Expired sessions will be replaced on next chat request
    return get_session_status(conv)


# =============================================================================
# Job Recovery Endpoints
# =============================================================================

@app.get("/api/jobs/active")
async def get_active_job_endpoint(user: AuthenticatedUser = Depends(get_current_user)):
    """Get the user's most recent unacknowledged running/complete job.

    Frontend calls this on reconnect/page load to recover missed responses.
    Returns null if no active job exists.
    """
    job = get_active_job(user.access_token, user.id)
    return {"job": job}


@app.get("/api/jobs/{job_id}")
async def get_job_endpoint(job_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get a specific job by ID."""
    job = get_job(user.access_token, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


@app.post("/api/jobs/{job_id}/ack")
async def acknowledge_job_endpoint(job_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Mark a job as acknowledged (client received the response).

    Prevents showing stale responses on next load.
    """
    acknowledge_job(user.access_token, job_id)
    return {"success": True}


@app.get("/api/debug/logging")
async def debug_logging():
    """Check current logging status (for debugging)."""
    from alfred.llm.prompt_logger import get_logging_status
    return get_logging_status()


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: AuthenticatedUser = Depends(get_current_user)):
    """Send a message to Alfred with streaming progress updates."""
    from alfred.llm.prompt_logger import enable_prompt_logging, set_user_id, get_session_log_dir

    # Convert ui_changes to dict format for workflow
    ui_changes_data = None
    if req.ui_changes:
        ui_changes_data = [c.model_dump() for c in req.ui_changes]

    # Create and start job before entering the generator
    job_id = create_job(user.access_token, user.id, {
        "message": req.message,
        "mode": req.mode,
        "ui_changes": ui_changes_data,
    })
    if job_id:
        start_job(user.access_token, job_id)

    async def event_generator():
        try:
            # Enable prompt logging based on user preference
            enable_prompt_logging(req.log_prompts)

            # Set user ID for logging context
            set_user_id(user.id)

            # Set request context for authenticated DB access
            set_request_context(access_token=user.access_token, user_id=user.id)

            # Get conversation from user's session (with DB fallback)
            conversation = get_user_conversation(user.id, user.access_token)

            # Stream Alfred's progress (will use authenticated client via request context)
            async for update in run_alfred_streaming(
                user_message=req.message,
                user_id=user.id,
                conversation=conversation,
                mode=req.mode,
                ui_changes=ui_changes_data,
            ):
                if update["type"] == "done":
                    # Get log directory
                    log_dir = get_session_log_dir()

                    # Complete job first, then commit conversation
                    if job_id:
                        try:
                            complete_job(user.access_token, job_id, {
                                "response": update["response"],
                                "active_context": update.get("active_context"),
                                "log_dir": str(log_dir) if log_dir else None,
                            })
                        except Exception as e:
                            logger.error(f"Failed to complete job {job_id}: {e}")

                    # Single commit: stamp metadata + cache + persist to DB
                    commit_conversation(user.id, user.access_token, update["conversation"], conversations)

                    yield {
                        "event": "done",
                        "data": json.dumps({
                            "response": update["response"],
                            "log_dir": str(log_dir) if log_dir else None,
                            "job_id": job_id,
                        }),
                    }
                elif update["type"] == "context_updated":
                    # Summarize completed async - commit final conversation
                    # Job output stays as original response — context_updated is internal state only
                    commit_conversation(user.id, user.access_token, update["conversation"], conversations)
                    yield {
                        "event": "context_updated",
                        "data": json.dumps({"status": "ready"}),
                    }
                else:
                    yield {
                        "event": "progress",
                        "data": json.dumps(update),
                    }
        except Exception as e:
            logger.exception("Stream chat error")
            if job_id:
                fail_job(user.access_token, job_id, str(e))
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
        finally:
            # Clear request context
            clear_request_context()

    return EventSourceResponse(event_generator())


# =============================================================================
# Data Endpoints
# =============================================================================

@app.get("/api/tables/inventory")
async def get_inventory(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's inventory."""
    client = get_authenticated_client(user.access_token)
    result = client.table("inventory").select("*").order("name").execute()
    return {"data": result.data}


@app.get("/api/tables/recipes")
async def get_recipes(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's recipes."""
    client = get_authenticated_client(user.access_token)
    result = client.table("recipes").select("*").order("created_at", desc=True).execute()
    return {"data": result.data}


@app.get("/api/ingredients/categories")
async def get_ingredient_categories(user: AuthenticatedUser = Depends(get_current_user)):
    """Get distinct ingredient categories."""
    client = get_authenticated_client(user.access_token)
    
    # Get total count
    count_result = client.table("ingredients").select("id", count="exact").execute()
    total = count_result.count or 0
    
    # Get distinct categories
    result = client.table("ingredients").select("category").execute()
    unique_cats = sorted(set(row.get("category") or "uncategorized" for row in result.data))
    
    categories = [{"category": cat} for cat in unique_cats]
    return {"data": categories, "total": total}


@app.get("/api/ingredients/by-category/{category}")
async def get_ingredients_by_category(category: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get ingredients for a specific category."""
    client = get_authenticated_client(user.access_token)
    if category.lower() == "uncategorized":
        result = client.table("ingredients").select("id, name, aliases, default_unit").is_("category", "null").order("name").execute()
    else:
        result = client.table("ingredients").select("id, name, aliases, default_unit").eq("category", category).order("name").execute()
    return {"data": result.data}


@app.get("/api/ingredients/search")
async def search_ingredients(q: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Search ingredients by name (limited results)."""
    client = get_authenticated_client(user.access_token)
    result = client.table("ingredients").select("id, name, category, aliases, default_unit").ilike("name", f"%{q}%").limit(50).execute()
    return {"data": result.data}


@app.get("/api/tables/recipes/{recipe_id}/ingredients")
async def get_recipe_ingredients(recipe_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get ingredients for a specific recipe."""
    client = get_authenticated_client(user.access_token)
    # RLS will ensure user can only see their own recipes
    recipe = client.table("recipes").select("id").eq("id", recipe_id).execute()
    if not recipe.data:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    result = client.table("recipe_ingredients").select("*").eq("recipe_id", recipe_id).execute()
    return {"data": result.data}


@app.get("/api/tables/shopping")
async def get_shopping_list(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's shopping list."""
    client = get_authenticated_client(user.access_token)
    result = client.table("shopping_list").select("*").order("name").execute()
    return {"data": result.data}


@app.get("/api/tables/meal_plans")
async def get_meal_plans(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's meal plans."""
    client = get_authenticated_client(user.access_token)
    result = client.table("meal_plans").select("*").order("date", desc=True).execute()
    return {"data": result.data}


@app.get("/api/tables/tasks")
async def get_tasks(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's tasks."""
    client = get_authenticated_client(user.access_token)
    result = client.table("tasks").select("*").order("due_date").execute()
    return {"data": result.data}


@app.get("/api/tables/cooking_log")
async def get_cooking_log(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's cooking history."""
    client = get_authenticated_client(user.access_token)
    result = client.table("cooking_log").select("*").order("cooked_at", desc=True).execute()
    return {"data": result.data}


@app.get("/api/tables/preferences")
async def get_preferences(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's preferences."""
    client = get_authenticated_client(user.access_token)
    result = client.table("preferences").select("*").execute()
    return {"data": result.data}


@app.get("/api/tables/flavor_preferences")
async def get_flavor_preferences(user: AuthenticatedUser = Depends(get_current_user)):
    """Get user's ingredient likes/dislikes with ingredient names."""
    client = get_authenticated_client(user.access_token)
    # Join with ingredients table to get names
    result = client.table("flavor_preferences").select("*, ingredients(name)").execute()
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
async def update_shopping_item(item_id: str, update: ShoppingItemUpdate, user: AuthenticatedUser = Depends(get_current_user)):
    """Update a shopping list item."""
    client = get_authenticated_client(user.access_token)
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # RLS ensures user can only update their own items
    result = client.table("shopping_list").update(update_data).eq("id", item_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"data": result.data[0]}

@app.patch("/api/tables/tasks/{task_id}")
async def update_task(task_id: str, update: TaskUpdate, user: AuthenticatedUser = Depends(get_current_user)):
    """Update a task."""
    client = get_authenticated_client(user.access_token)
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = client.table("tasks").update(update_data).eq("id", task_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"data": result.data[0]}

@app.patch("/api/tables/inventory/{item_id}")
async def update_inventory_item(item_id: str, update: InventoryUpdate, user: AuthenticatedUser = Depends(get_current_user)):
    """Update an inventory item."""
    client = get_authenticated_client(user.access_token)
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = client.table("inventory").update(update_data).eq("id", item_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"data": result.data[0]}

@app.patch("/api/tables/meal_plans/{meal_plan_id}")
async def update_meal_plan(meal_plan_id: str, update: MealPlanUpdate, user: AuthenticatedUser = Depends(get_current_user)):
    """Update a meal plan."""
    client = get_authenticated_client(user.access_token)
    
    update_data = {}
    for k, v in update.model_dump().items():
        if k == 'recipe_id':
            if v is not None or 'recipe_id' in update.model_dump(exclude_unset=True):
                update_data[k] = v
        elif v is not None:
            update_data[k] = v
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = client.table("meal_plans").update(update_data).eq("id", meal_plan_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    
    return {"data": result.data[0]}

@app.delete("/api/tables/{table}/{item_id}")
async def delete_item(table: str, item_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Delete an item from a table."""
    allowed_tables = {"inventory", "shopping_list", "tasks", "recipes", "meal_plans"}
    if table not in allowed_tables:
        raise HTTPException(status_code=400, detail=f"Table {table} not allowed")
    
    client = get_authenticated_client(user.access_token)
    # RLS ensures user can only delete their own items
    result = client.table(table).delete().eq("id", item_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"success": True}


# =============================================================================
# Frontend - React SPA
# =============================================================================

def find_frontend_dir() -> Path | None:
    """Find the React build directory in dev or Docker."""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "frontend" / "dist",
        Path("/app/frontend/dist"),
        Path.cwd() / "frontend" / "dist",
    ]
    for path in candidates:
        if path.exists() and (path / "index.html").exists():
            return path
    return None

FRONTEND_DIR = find_frontend_dir()

if FRONTEND_DIR is not None:
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA - all routes return index.html, React Router handles routing."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
        return FileResponse(FRONTEND_DIR / "index.html")
else:
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
