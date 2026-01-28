"""
Onboarding API Endpoints.

Separate router from Alfred's main /chat endpoints.
Handles the onboarding flow with persistent state management.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from .state import (
    OnboardingState,
    OnboardingPhase,
    get_next_phase,
    can_skip_phase,
)
from .payload import OnboardingPayload, build_payload_from_state
from .forms import ConstraintsForm, validate_constraints, get_form_options
from .filters import get_constraints_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# Auth - reuse from main app
# =============================================================================

class AuthenticatedUser(BaseModel):
    """Authenticated user info from Supabase JWT."""
    id: str
    email: str | None
    access_token: str


async def get_current_user(authorization: str = Header(None)) -> AuthenticatedUser:
    """
    Validate Supabase JWT and extract user info.
    
    Expects: Authorization: Bearer <supabase_access_token>
    """
    from alfred.db.client import get_service_client
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        client = get_service_client()
        # Verify token with Supabase
        user_response = client.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return AuthenticatedUser(
            id=user_response.user.id,
            email=user_response.user.email,
            access_token=token,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


# =============================================================================
# Request/Response Models
# =============================================================================


class ConstraintsRequest(BaseModel):
    """Phase 1: Hard constraints form data."""
    household_size: int = Field(ge=1, le=12, default=2)
    allergies: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    cooking_skill_level: str = Field(default="intermediate")
    available_equipment: list[str] = Field(default_factory=list)


class CuisineRequest(BaseModel):
    """Phase 2c: Cuisine selections."""
    cuisines: list[str] = Field(default_factory=list)


class StaplesRequest(BaseModel):
    """Phase 2d: Staples selection (ingredients user always keeps stocked)."""
    ingredient_ids: list[str] = Field(default_factory=list)


class StyleFeedbackRequest(BaseModel):
    """Phase 3: Style selection feedback."""
    domain: str  # "recipes", "meal_plans", or "tasks"
    selection: str | None = None  # ID of selected sample
    feedback: str = ""  # Natural language feedback
    samples_shown: list[dict] = Field(default_factory=list)  # Samples that were shown to user


class HabitsRequest(BaseModel):
    """Phase 3: Habits free-form response."""
    response: str


class PreviewFeedbackRequest(BaseModel):
    """Phase 4: Preview feedback."""
    feedback: list[dict] = Field(default_factory=list)
    # Each: {"recipe_id": str, "sentiment": "positive" | "negative"}


class SkipPhaseRequest(BaseModel):
    """Skip current phase."""
    phase: str  # Phase to skip


class InterviewAnswerRequest(BaseModel):
    """Submit answers for an interview page."""
    page_number: int = Field(ge=1, le=4)
    answers: list[dict] = Field(default_factory=list)
    # Each: {"question_id": str, "question": str, "answer": str}


class InterviewSynthesisRequest(BaseModel):
    """Request to synthesize all interview answers into guidance."""
    all_answers: list[dict] = Field(default_factory=list)


class StateResponse(BaseModel):
    """Current onboarding state response."""
    user_id: str
    current_phase: str  # maps to frontend's `phase`
    phase: str = ""  # alias for frontend compatibility
    phases_completed: list[str]
    payload_preview: dict
    # Flattened fields for frontend resume logic
    constraints: dict | None = None
    initial_inventory: list = []
    cuisine_preferences: list = []
    ingredient_preferences: dict = {}


class PhaseResponse(BaseModel):
    """Response after completing a phase."""
    success: bool
    current_phase: str
    next_phase: str | None
    message: str = ""


# =============================================================================
# State Management Helpers
# =============================================================================


async def get_or_create_session(user_id: str) -> OnboardingState:
    """
    Load existing session or create new one.
    
    Called at start of any onboarding endpoint.
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    try:
        # Try to load existing session
        result = client.table("onboarding_sessions").select("*").eq("user_id", user_id).execute()
        
        if result.data:
            session_data = result.data[0]
            state = OnboardingState.from_dict(session_data["state"])
            return state
    except Exception as e:
        logger.warning(f"Failed to load onboarding session: {e}")
    
    # Create new session
    state = OnboardingState(user_id=user_id)
    await save_session(state)
    return state


async def save_session(state: OnboardingState) -> None:
    """
    Save session state to database.
    
    Called after every step to ensure durability.
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    state.updated_at = datetime.utcnow().isoformat()
    
    try:
        client.table("onboarding_sessions").upsert({
            "user_id": state.user_id,
            "state": state.to_dict(),
            "current_phase": state.current_phase.value,
            "updated_at": state.updated_at,
        }).execute()
    except Exception as e:
        logger.error(f"Failed to save onboarding session: {e}")
        raise HTTPException(status_code=500, detail="Failed to save session")


async def clear_session(user_id: str) -> None:
    """Delete onboarding session after completion."""
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    try:
        client.table("onboarding_sessions").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning(f"Failed to clear onboarding session: {e}")


def get_completed_phases(state: OnboardingState) -> list[str]:
    """Get list of completed phase names."""
    completed = []
    phase_order = list(OnboardingPhase)
    current_idx = phase_order.index(state.current_phase)
    
    for phase in phase_order[:current_idx]:
        completed.append(phase.value)
    
    return completed


# =============================================================================
# Endpoints: State Management
# =============================================================================


@router.get("/state", response_model=StateResponse)
async def get_onboarding_state(user: AuthenticatedUser = Depends(get_current_user)) -> StateResponse:
    """Get current onboarding progress."""
    from alfred.db.client import get_service_client

    client = get_service_client()

    # First check if user already completed onboarding
    completed = client.table("onboarding_data").select("user_id").eq("user_id", user.id).limit(1).execute()
    if completed.data:
        # Already completed - don't create new session
        return StateResponse(
            user_id=user.id,
            current_phase="complete",
            phase="complete",
            phases_completed=["constraints", "cuisines", "staples", "style_recipes"],
            payload_preview={},
            constraints={},
            initial_inventory=[],
            cuisine_preferences=[],
            ingredient_preferences={"likes": 0, "dislikes": 0},
        )

    # Check for in-progress session or create new one
    state = await get_or_create_session(user.id)

    return StateResponse(
        user_id=state.user_id,
        current_phase=state.current_phase.value,
        phase=state.current_phase.value,  # Frontend expects 'phase'
        phases_completed=get_completed_phases(state),
        payload_preview=state.payload_draft,
        # Flattened fields for frontend resume logic
        constraints=state.constraints if state.constraints else None,
        initial_inventory=state.pantry_items,
        cuisine_preferences=state.cuisine_selections,
        ingredient_preferences={"likes": 0, "dislikes": 0},
    )


@router.post("/skip", response_model=PhaseResponse)
async def skip_phase(request: SkipPhaseRequest, user: AuthenticatedUser = Depends(get_current_user)) -> PhaseResponse:
    """Skip the current phase if skippable."""
    state = await get_or_create_session(user.id)
    
    try:
        target_phase = OnboardingPhase(request.phase)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown phase: {request.phase}")
    
    if target_phase != state.current_phase:
        raise HTTPException(
            status_code=400, 
            detail=f"Can only skip current phase ({state.current_phase.value})"
        )
    
    if not can_skip_phase(target_phase):
        raise HTTPException(
            status_code=400,
            detail=f"Phase {target_phase.value} cannot be skipped"
        )
    
    # Force transition to next phase
    next_phase = get_next_phase(state)
    if next_phase == state.current_phase:
        # Manual skip - find next in order
        phase_order = list(OnboardingPhase)
        current_idx = phase_order.index(state.current_phase)
        if current_idx + 1 < len(phase_order):
            next_phase = phase_order[current_idx + 1]
    
    state.current_phase = next_phase
    await save_session(state)
    
    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=get_next_phase(state).value if state.current_phase != OnboardingPhase.COMPLETE else None,
        message=f"Skipped to {state.current_phase.value}",
    )


# =============================================================================
# Endpoints: Phase 1 - Constraints
# =============================================================================


@router.get("/constraints/options")
async def get_constraints_options():
    """
    Get form options for constraints (Phase 1).
    
    Returns allergens, dietary restrictions, equipment, and skill levels
    with display metadata for frontend rendering.
    """
    return get_form_options()


@router.post("/constraints", response_model=PhaseResponse)
async def submit_constraints(request: ConstraintsRequest, user: AuthenticatedUser = Depends(get_current_user)) -> PhaseResponse:
    """Submit hard constraints form (Phase 1)."""
    state = await get_or_create_session(user.id)
    
    # Validate using ConstraintsForm
    try:
        form = ConstraintsForm(
            household_size=request.household_size,
            allergies=request.allergies,
            dietary_restrictions=request.dietary_restrictions,
            cooking_skill_level=request.cooking_skill_level,
            available_equipment=request.available_equipment,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Additional validation
    is_valid, errors = validate_constraints(form)
    if not is_valid:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    
    # Store validated constraints
    state.constraints = {
        "household_size": form.household_size,
        "allergies": form.allergies,
        "dietary_restrictions": form.dietary_restrictions,
        "cooking_skill_level": form.cooking_skill_level,
        "available_equipment": form.available_equipment,
    }
    
    # Update payload draft with preferences
    state.payload_draft["preferences"] = state.constraints
    
    # Transition to next phase
    state.current_phase = get_next_phase(state)
    await save_session(state)
    
    summary = get_constraints_summary(state.constraints)
    
    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=get_next_phase(state).value,
        message=f"Constraints saved: {summary}",
    )


# =============================================================================
# Endpoints: Phase 2 - Cuisines & Staples
# =============================================================================


# -----------------------------------------------------------------------------
# Cuisine Selection
# -----------------------------------------------------------------------------

@router.get("/cuisines/options")
async def get_cuisine_options():
    """Get cuisine options for selection."""
    from .cuisine_selection import get_cuisine_options, MAX_CUISINE_SELECTIONS
    
    return {
        "options": get_cuisine_options(),
        "max_selections": MAX_CUISINE_SELECTIONS,
    }


@router.post("/cuisines", response_model=PhaseResponse)
async def submit_cuisines(request: CuisineRequest, user: AuthenticatedUser = Depends(get_current_user)) -> PhaseResponse:
    """Submit cuisine selections."""
    from .cuisine_selection import validate_cuisine_selections
    
    state = await get_or_create_session(user.id)
    
    # Validate cuisines
    valid_cuisines = validate_cuisine_selections(request.cuisines)
    
    state.cuisine_selections = valid_cuisines
    state.payload_draft["cuisine_preferences"] = valid_cuisines
    
    # Don't auto-advance - user controls when to move on
    await save_session(state)
    
    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=get_next_phase(state).value,
        message=f"Cuisines saved ({len(valid_cuisines)} selected)",
    )


# -----------------------------------------------------------------------------
# Staples Selection (Phase 2b)
# -----------------------------------------------------------------------------


@router.get("/staples/options")
async def get_staples_options(
    cuisines: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get staples options grouped by parent_category.

    Query params:
        cuisines: Comma-separated list of cuisine codes (e.g., "indian,thai")

    Returns:
        {
            "categories": [...],
            "pre_selected_ids": [...],
            "cuisine_suggested_ids": [...]
        }
    """
    from .staples import get_staples_options

    # Parse cuisines from query param
    cuisine_list = []
    if cuisines:
        cuisine_list = [c.strip() for c in cuisines.split(",") if c.strip()]

    return await get_staples_options(cuisines=cuisine_list)


@router.post("/staples", response_model=PhaseResponse)
async def submit_staples(
    request: StaplesRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PhaseResponse:
    """
    Submit staples selection.

    Saves selected ingredient IDs to state.staple_selections.
    Advances phase to STYLE_RECIPES.
    """
    from .staples import validate_staple_selections

    state = await get_or_create_session(user.id)

    # Validate ingredient IDs
    valid_ids = validate_staple_selections(request.ingredient_ids)

    state.staple_selections = valid_ids

    # Advance to next phase (STAPLES → STYLE_RECIPES)
    state.current_phase = OnboardingPhase.STAPLES
    next_phase = get_next_phase(state)
    state.current_phase = next_phase

    await save_session(state)

    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=get_next_phase(state).value,
        message=f"Staples saved ({len(valid_ids)} selected)",
    )


# =============================================================================
# Endpoints: Phase 3 - Style Interview
# =============================================================================


@router.get("/interview/page/{page_number}")
async def get_interview_page(
    page_number: int,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get an interview page with LLM-generated questions.
    
    Pages 1-3 have structured data points, page 4 is catch-all.
    Questions are personalized based on user context and prior answers.
    """
    from .style_interview import generate_interview_page, generate_catchall_page
    
    if page_number < 1 or page_number > 4:
        raise HTTPException(status_code=400, detail="Page number must be 1-4")
    
    state = await get_or_create_session(user.id)
    
    # Build user context from collected data
    user_context = {
        "cooking_skill_level": state.constraints.get("cooking_skill_level", "intermediate"),
        "household_size": state.constraints.get("household_size", 2),
        "dietary_restrictions": state.constraints.get("dietary_restrictions", []),
        "available_equipment": state.constraints.get("available_equipment", []),
        "cuisines": state.cuisine_selections,
        "liked_ingredients": [item.get("name", "") for item in state.pantry_items[:10]],
    }
    
    # Get prior answers from state
    prior_answers = state.payload_draft.get("interview_answers", [])
    
    try:
        if page_number <= 3:
            page = await generate_interview_page(
                page_number=page_number,
                user_context=user_context,
                prior_answers=prior_answers,
            )
            return {
                "page_number": page_number,
                "title": page.title,
                "subtitle": page.subtitle,
                "questions": [q.model_dump() for q in page.questions],
                "is_catchall": False,
            }
        else:  # page 4 = catch-all
            catchall = await generate_catchall_page(
                user_context=user_context,
                all_answers=prior_answers,
            )
            return {
                "page_number": 4,
                "title": "Almost Done",
                "subtitle": catchall.subtitle,
                "questions": [q.model_dump() for q in catchall.questions],
                "is_catchall": True,
                "ready_to_proceed": catchall.ready_to_proceed,
            }
    except Exception as e:
        logger.error(f"Failed to generate interview page {page_number}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")


@router.post("/interview/page/{page_number}")
async def submit_interview_page(
    page_number: int,
    request: InterviewAnswerRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Submit answers for an interview page.
    
    Stores answers and returns next page number or synthesis-ready status.
    """
    if page_number < 1 or page_number > 4:
        raise HTTPException(status_code=400, detail="Page number must be 1-4")
    
    state = await get_or_create_session(user.id)
    
    # Initialize interview_answers if needed
    if "interview_answers" not in state.payload_draft:
        state.payload_draft["interview_answers"] = []
    
    # Add new answers (with page context)
    for ans in request.answers:
        state.payload_draft["interview_answers"].append({
            "page": page_number,
            "question_id": ans.get("question_id", ""),
            "question": ans.get("question", ""),
            "answer": ans.get("answer", ""),
        })
    
    await save_session(state)
    
    # Determine next step
    if page_number < 4:
        return {
            "success": True,
            "next_page": page_number + 1,
            "message": f"Page {page_number} saved",
        }
    else:
        return {
            "success": True,
            "next_page": None,
            "ready_for_synthesis": True,
            "message": "Interview complete, ready for synthesis",
        }


@router.post("/interview/synthesize")
async def synthesize_interview(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Synthesize all interview answers into subdomain_guidance strings.
    
    Called after all interview pages are complete.
    Returns guidance strings that will be stored in payload.
    """
    from .style_interview import synthesize_guidance
    
    state = await get_or_create_session(user.id)
    
    # Build user context
    user_context = {
        "cooking_skill_level": state.constraints.get("cooking_skill_level", "intermediate"),
        "household_size": state.constraints.get("household_size", 2),
        "dietary_restrictions": state.constraints.get("dietary_restrictions", []),
        "available_equipment": state.constraints.get("available_equipment", []),
        "cuisines": state.cuisine_selections,
        "liked_ingredients": [item.get("name", "") for item in state.pantry_items[:10]],
    }
    
    all_answers = state.payload_draft.get("interview_answers", [])
    
    if not all_answers:
        raise HTTPException(status_code=400, detail="No interview answers to synthesize")
    
    try:
        guidance = await synthesize_guidance(
            user_context=user_context,
            all_answers=all_answers,
        )
        
        # Store draft guidance in payload
        state.payload_draft["subdomain_guidance"] = {
            "recipes": guidance.recipes,
            "meal_plans": guidance.meal_plans,
            "tasks": guidance.tasks,
            "shopping": guidance.shopping,
            "inventory": guidance.inventory,
        }
        
        await save_session(state)
        
        return {
            "success": True,
            "subdomain_guidance": state.payload_draft["subdomain_guidance"],
            "message": "Guidance synthesized from interview",
        }
        
    except Exception as e:
        logger.error(f"Failed to synthesize interview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to synthesize: {str(e)}")


# =============================================================================
# Endpoints: Phase 3 - Style Samples (Optional Refinement)
# =============================================================================


@router.get("/style/samples/{domain}")
async def get_style_samples(domain: str, user: AuthenticatedUser = Depends(get_current_user)):
    """
    Get LLM-generated style samples for a domain.
    
    Uses user's pantry, cuisines, and constraints to generate personalized samples.
    """
    from .style_discovery import (
        generate_recipe_style_samples,
        generate_meal_plan_style_samples,
        generate_task_style_samples,
    )
    
    state = await get_or_create_session(user.id)
    
    if domain not in ("recipes", "meal_plans", "tasks"):
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain}")
    
    # Build payload_draft for LLM context
    payload_draft = {
        "preferences": state.constraints,
        "initial_inventory": state.pantry_items,
        "cuisine_preferences": state.cuisine_selections,
    }
    
    try:
        if domain == "recipes":
            proposal = await generate_recipe_style_samples(payload_draft)
            samples = [
                {
                    "id": s.id,
                    "style_name": s.style_name,
                    "style_tags": s.style_tags,
                    "text": s.recipe_text,
                    "why_this_style": s.why_this_style,
                }
                for s in proposal.samples
            ]
            return {
                "domain": domain,
                "dish_name": proposal.dish_name,
                "intro_message": proposal.intro_message,
                "samples": samples,
            }
        
        elif domain == "meal_plans":
            proposal = await generate_meal_plan_style_samples(payload_draft)
            samples = [
                {
                    "id": s.id,
                    "style_name": s.style_name,
                    "text": s.plan_text,
                    "why_this_style": s.why_this_style,
                }
                for s in proposal.samples
            ]
            return {
                "domain": domain,
                "intro_message": proposal.intro_message,
                "samples": samples,
            }
        
        else:  # tasks
            proposal = await generate_task_style_samples(payload_draft)
            samples = [
                {
                    "id": s.id,
                    "style_name": s.style_name,
                    "text": s.task_text,
                    "why_this_style": s.why_this_style,
                }
                for s in proposal.samples
            ]
            return {
                "domain": domain,
                "intro_message": proposal.intro_message,
                "samples": samples,
            }
            
    except Exception as e:
        logger.error(f"Failed to generate {domain} style samples: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate style samples: {str(e)}")


@router.post("/style/feedback", response_model=PhaseResponse)
async def submit_style_feedback(
    request: StyleFeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PhaseResponse:
    """
    Submit style selection feedback (Phase 3).
    
    Calls LLM to synthesize user's selection/feedback into subdomain_guidance.
    """
    from .style_discovery import synthesize_style_feedback
    
    state = await get_or_create_session(user.id)
    
    if request.domain not in ("recipes", "meal_plans", "tasks"):
        raise HTTPException(status_code=400, detail=f"Unknown domain: {request.domain}")
    
    # Get the appropriate style state
    style_state = getattr(state, f"style_{request.domain}")
    style_state.user_selection = request.selection
    style_state.user_feedback = request.feedback
    style_state.samples_shown = request.samples_shown  # Store for reference
    style_state.completed = True
    
    # Call LLM to synthesize feedback into guidance
    try:
        synthesis = await synthesize_style_feedback(
            domain=request.domain,
            samples_shown=request.samples_shown,
            user_selection=request.selection,
            user_feedback=request.feedback or "",
        )
        
        # Store guidance in payload_draft
        state.payload_draft.setdefault("subdomain_guidance", {})[request.domain] = synthesis.guidance_summary
        
        acknowledgment = synthesis.acknowledgment
        
    except Exception as e:
        logger.warning(f"Failed to synthesize {request.domain} feedback: {e}")
        # Fallback: use feedback directly if synthesis fails
        if request.feedback:
            state.payload_draft.setdefault("subdomain_guidance", {})[request.domain] = request.feedback
        acknowledgment = f"Got it — your {request.domain.replace('_', ' ')} preferences saved."
    
    # Transition to next phase
    state.current_phase = get_next_phase(state)
    await save_session(state)
    
    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=get_next_phase(state).value,
        message=acknowledgment,
    )


@router.post("/habits", response_model=PhaseResponse)
async def submit_habits(request: HabitsRequest, user: AuthenticatedUser = Depends(get_current_user)) -> PhaseResponse:
    """
    Submit habits free-form response (Phase 3).
    
    Calls LLM to extract structured habits and generate subdomain guidance
    for meal_plans, shopping, and inventory.
    """
    from .style_discovery import extract_habits
    
    state = await get_or_create_session(user.id)
    
    state.habits_response = request.response
    
    # Call LLM to extract structured habits
    try:
        extraction = await extract_habits(
            user_response=request.response,
            constraints=state.constraints,
        )
        
        state.habits_extraction = {
            "cooking_frequency": extraction.cooking_frequency,
            "batch_cooking": extraction.batch_cooking,
            "cooking_days": extraction.cooking_days,
            "leftover_tolerance_days": extraction.leftover_tolerance_days,
            "shopping_frequency": extraction.shopping_frequency,
            "meal_plans_summary": extraction.meal_plans_summary,
            "shopping_summary": extraction.shopping_summary,
            "inventory_summary": extraction.inventory_summary,
            "raw_response": request.response,
        }
        
        # Apply summaries to subdomain_guidance
        guidance = state.payload_draft.setdefault("subdomain_guidance", {})
        if extraction.meal_plans_summary:
            # Append to existing or set new
            existing = guidance.get("meal_plans", "")
            if existing:
                guidance["meal_plans"] = f"{existing} {extraction.meal_plans_summary}"
            else:
                guidance["meal_plans"] = extraction.meal_plans_summary
        if extraction.shopping_summary:
            guidance["shopping"] = extraction.shopping_summary
        if extraction.inventory_summary:
            guidance["inventory"] = extraction.inventory_summary
        
        message = "Got it! I've noted your cooking and shopping habits."
        
    except Exception as e:
        logger.warning(f"Failed to extract habits: {e}")
        # Fallback: store raw response
        state.habits_extraction = {
            "raw_response": request.response,
        }
        message = "Habits saved."
    
    # Transition to next phase
    state.current_phase = get_next_phase(state)
    await save_session(state)
    
    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=get_next_phase(state).value,
        message=message,
    )


# =============================================================================
# Endpoints: Phase 4 - Preview & Complete
# =============================================================================


@router.get("/preview/recipes")
async def get_preview_recipes(count: int = 3, user: AuthenticatedUser = Depends(get_current_user)):
    """Generate sample recipes based on collected preferences."""
    state = await get_or_create_session(user.id)
    
    # TODO: Implement recipe generation
    # For now, return placeholder
    return {
        "recipes": [],  # Will be populated by generation logic
        "message": "Based on your preferences, here are some recipes you might enjoy...",
    }


@router.post("/preview/feedback", response_model=PhaseResponse)
async def submit_preview_feedback(
    request: PreviewFeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PhaseResponse:
    """Submit preview feedback (Phase 4)."""
    state = await get_or_create_session(user.id)
    
    state.preview_feedback = request.feedback
    
    # Log feedback for future analysis
    logger.info(f"Preview feedback for {user.id}: {request.feedback}")
    
    await save_session(state)
    
    return PhaseResponse(
        success=True,
        current_phase=state.current_phase.value,
        next_phase=OnboardingPhase.COMPLETE.value,
        message="Feedback recorded",
    )


@router.post("/complete")
async def complete_onboarding(user: AuthenticatedUser = Depends(get_current_user)):
    """
    Finalize onboarding, store payload, and apply to Alfred preferences.
    
    1. Stores complete payload to onboarding_data table
    2. Applies preferences to Alfred's preferences table (auto-apply)
    3. Clears the onboarding session
    
    If user skipped style discovery, subdomain_guidance may be empty - that's fine,
    Alfred works without personalization.
    """
    state = await get_or_create_session(user.id)
    
    # Build final payload
    payload = build_payload_from_state(state)
    payload_dict = payload.to_dict()
    
    from alfred.db.client import get_service_client
    client = get_service_client()
    
    try:
        # 1. Store payload to onboarding_data table
        client.table("onboarding_data").upsert({
            "user_id": user.id,
            "payload": payload_dict,
            "version": payload.onboarding_version,
            "completed_at": datetime.utcnow().isoformat(),
        }).execute()
        
        # 2. Auto-apply to preferences table
        # Note: payload uses "preferences" key, not "constraints"
        prefs = payload_dict.get("preferences", {})
        prefs_data = {
            "user_id": user.id,
            "dietary_restrictions": prefs.get("dietary_restrictions", []),
            "allergies": prefs.get("allergies", []),
            "cooking_skill_level": prefs.get("cooking_skill_level", "intermediate"),
            "household_size": prefs.get("household_size", 1),
            "available_equipment": prefs.get("available_equipment", []),
            "favorite_cuisines": payload_dict.get("cuisine_preferences", []),
            "subdomain_guidance": payload_dict.get("subdomain_guidance", {}),
            "assumed_staples": payload_dict.get("assumed_staples", []),
        }
        
        client.table("preferences").upsert(
            prefs_data,
            on_conflict="user_id"
        ).execute()
        
        logger.info(f"Onboarding completed and applied for user {user.id}")
        
        # 3. Clear session (onboarding complete)
        await clear_session(user.id)
        
        return {
            "success": True,
            "message": "Onboarding complete! Your preferences are now active in Alfred.",
            "payload": payload_dict,
            "applied_to_preferences": True,
        }
        
    except Exception as e:
        logger.error(f"Failed to complete onboarding: {e}")
        raise HTTPException(status_code=500, detail="Failed to save onboarding data")


@router.post("/apply")
async def apply_onboarding_to_preferences(user: AuthenticatedUser = Depends(get_current_user)):
    """
    Apply onboarding data to Alfred's preferences table.
    
    Transfers:
    - constraints → dietary_restrictions, allergies, cooking_skill_level, household_size, available_equipment
    - cuisine_preferences → favorite_cuisines
    - subdomain_guidance → subdomain_guidance (injected into prompts)
    
    Can be called after /complete or separately to re-apply.
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    # 1. Fetch onboarding payload
    result = client.table("onboarding_data").select("payload").eq("user_id", user.id).limit(1).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="No onboarding data found. Complete onboarding first.")
    
    payload = result.data[0]["payload"]
    constraints = payload.get("constraints", {})
    
    # 2. Build preferences upsert
    # Note: payload uses "preferences" key (from OnboardingPayload.preferences)
    prefs = payload.get("preferences", constraints)  # Fallback to constraints for older payloads
    prefs_data = {
        "user_id": user.id,
        # Hard constraints
        "dietary_restrictions": prefs.get("dietary_restrictions", []),
        "allergies": prefs.get("allergies", []),
        "cooking_skill_level": prefs.get("cooking_skill_level", "intermediate"),
        "household_size": prefs.get("household_size", 1),
        # Equipment (used by recipes/meal_plans)
        "available_equipment": prefs.get("available_equipment", []),
        # Taste preferences
        "favorite_cuisines": payload.get("cuisine_preferences", []),
        # Subdomain guidance (injected into Think/Act prompts)
        "subdomain_guidance": payload.get("subdomain_guidance", {}),
        # Assumed staples (user-confirmed always-stocked ingredients)
        "assumed_staples": payload.get("assumed_staples", []),
    }
    
    # 3. UPSERT to preferences table
    try:
        client.table("preferences").upsert(
            prefs_data,
            on_conflict="user_id"
        ).execute()
        
        logger.info(f"Applied onboarding to preferences for user {user.id}")
        
        return {
            "success": True,
            "message": "Onboarding preferences applied to Alfred",
            "applied": {
                "dietary_restrictions": prefs_data["dietary_restrictions"],
                "allergies": prefs_data["allergies"],
                "cooking_skill_level": prefs_data["cooking_skill_level"],
                "household_size": prefs_data["household_size"],
                "available_equipment": prefs_data["available_equipment"],
                "favorite_cuisines": prefs_data["favorite_cuisines"],
                "subdomain_guidance_keys": list(prefs_data["subdomain_guidance"].keys()),
                "assumed_staples_count": len(prefs_data["assumed_staples"]),
            },
        }
        
    except Exception as e:
        logger.error(f"Failed to apply onboarding to preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply preferences: {str(e)}")
