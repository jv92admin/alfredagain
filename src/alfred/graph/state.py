"""
Alfred V2 - Graph State Definition.

The AlfredState is the shared state passed through all nodes.
"""

from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


# =============================================================================
# Context Token Thresholds
# =============================================================================

# Router and Think get condensed context (fast routing/planning)
ROUTER_CONTEXT_THRESHOLD = 8_000  # tokens

# Act gets full recent context (needs details for execution)
ACT_CONTEXT_THRESHOLD = 25_000  # tokens (we have 400K window)

# How many turns/steps to keep in full detail
FULL_DETAIL_TURNS = 3  # Last 3 conversation turns
FULL_DETAIL_STEPS = 3  # Last 3 step results (important for multi-step flows)


# =============================================================================
# Entity Reference Pattern
# =============================================================================


class EntityRef(BaseModel):
    """
    Safe object reference used throughout the system.

    Rules:
    - Tools always return EntityRefs
    - Tools accept IDs, not raw strings
    - LLMs never fabricate IDs
    """

    type: str  # "ingredient", "recipe", "meal_plan", "inventory_item"
    id: str  # UUID
    label: str  # Human-readable for LLM context
    source: str  # "db_lookup", "user_input", "generated"
    step_index: int | None = None  # Which step this came from (for retrieval)


# =============================================================================
# Core Contracts
# =============================================================================


class RouterOutput(BaseModel):
    """Output from the Router node."""

    agent: Literal["pantry", "coach", "cellar"]
    goal: str  # Natural language
    complexity: Literal["low", "medium", "high"]
    # NOTE: No context_needs - Act handles ALL data access via CRUD


class PlannedStep(BaseModel):
    """
    A step in the execution plan with subdomain hint.
    
    Think node outputs these - each step has:
    - A natural language description
    - A step type (crud, analyze, or generate)
    - A subdomain hint (Act gets schema for CRUD steps)
    - Complexity for model selection
    """

    description: str  # Natural language step description
    step_type: Literal["crud", "analyze", "generate"] = "crud"
    subdomain: str  # "inventory", "recipes", "shopping", "meal_plans", "preferences"
    complexity: Literal["low", "medium", "high"] = "low"


class ThinkOutput(BaseModel):
    """
    Output from the Think node.
    
    Think can decide to:
    - plan_direct: Proceed with execution (simple, unambiguous requests)
    - propose: State assumptions and ask for confirmation (complex requests with known context)
    - clarify: Ask questions before planning (missing critical context)
    """

    # Decision determines the flow
    decision: Literal["plan_direct", "propose", "clarify"] = "plan_direct"
    
    # Always present
    goal: str
    
    # If plan_direct: steps to execute
    steps: list[PlannedStep] = Field(default_factory=list)
    
    # If propose: state assumptions for user to confirm/correct
    proposal_message: str | None = None
    assumptions: list[str] | None = None
    
    # If clarify: questions to ask before planning
    clarification_questions: list[str] | None = None


# =============================================================================
# Act Loop Actions
# =============================================================================


class ToolCallAction(BaseModel):
    """Request to call a CRUD tool."""

    action: Literal["tool_call"] = "tool_call"
    tool: Literal["db_read", "db_create", "db_update", "db_delete"]
    params: dict[str, Any]  # Tool-specific params


class StepCompleteAction(BaseModel):
    """Indicates a step was completed successfully."""

    action: Literal["step_complete"] = "step_complete"
    result_summary: str  # Brief description of outcome
    data: Any = None  # Full result for caching
    note_for_next_step: str | None = None  # Short note for next step (IDs, counts, etc.)


class RequestSchemaAction(BaseModel):
    """Request additional subdomain schema."""

    action: Literal["request_schema"] = "request_schema"
    subdomain: str  # Request schema for this subdomain


class RetrieveStepAction(BaseModel):
    """Request to retrieve full data from an older step."""

    action: Literal["retrieve_step"] = "retrieve_step"
    step_index: int  # 0-based index of step to retrieve


class AskUserAction(BaseModel):
    """Request clarification from the user."""

    action: Literal["ask_user"] = "ask_user"
    question: str  # Clear, single question
    context: str  # Why we need this info


class BlockedAction(BaseModel):
    """Indicates the agent is stuck and needs orchestrator intervention."""

    action: Literal["blocked"] = "blocked"
    reason_code: Literal[
        "INSUFFICIENT_INFO",  # Need user input
        "PLAN_INVALID",  # Current plan won't work
        "TOOL_FAILURE",  # Tool returned error
    ]
    details: str  # Human-readable explanation
    suggested_next: Literal["ask_user", "replan", "fail"]


class FailAction(BaseModel):
    """Indicates unrecoverable failure."""

    action: Literal["fail"] = "fail"
    reason: str  # Why we can't proceed
    user_message: str  # What to tell the user


# Union type for all actions
ActAction = (
    ToolCallAction
    | StepCompleteAction
    | RequestSchemaAction
    | RetrieveStepAction
    | AskUserAction
    | BlockedAction
    | FailAction
)


# =============================================================================
# Conversation Context (Phase 5)
# =============================================================================


class ConversationTurn(BaseModel):
    """A single turn in the conversation."""
    
    user: str  # User's message
    assistant: str  # Alfred's full response (for Reply/display)
    assistant_summary: str | None = None  # LLM-condensed version (for context in Act/Think)
    timestamp: str  # ISO format
    routing: dict[str, Any] | None = None  # Router decision for this turn
    entities_mentioned: list[str] = Field(default_factory=list)  # Entity IDs touched


class StepSummary(BaseModel):
    """Compressed summary of an older step (beyond FULL_DETAIL_STEPS)."""
    
    step_index: int
    description: str  # From the plan
    subdomain: str
    outcome: str  # One-line summary
    entity_ids: list[str] = Field(default_factory=list)  # IDs for retrieval
    record_count: int = 0  # How many records were involved


class ConversationContext(TypedDict, total=False):
    """
    Conversation history and context tracking.
    
    Design:
    - Last FULL_DETAIL_TURNS turns: full text
    - Older turns: compressed to history_summary
    - Last FULL_DETAIL_STEPS step results: full data in step_results
    - Older steps: compressed to step_summaries (Act can retrieve via tool)
    - active_entities: EntityRefs for "that recipe" resolution
    """

    # High-level summary of current engagement
    engagement_summary: str  # "Helping with meal planning, saved 2 recipes..."

    # Last N exchanges - full text (N = FULL_DETAIL_TURNS)
    recent_turns: list[dict]  # ConversationTurn as dict

    # Older exchanges - compressed
    history_summary: str  # "Earlier discussed pasta, added milk to pantry..."
    
    # Older step summaries (for reference, Act can retrieve full data)
    step_summaries: list[dict]  # StepSummary as dict

    # Content archive for generated content (persists across turns)
    # Allows "save those recipes we discussed" to work in later turns
    # Keys: "generated_recipes", "generated_meal_plan", "analysis_result", etc.
    content_archive: dict[str, Any]
    
    # Tracked entities for "that recipe" resolution
    # Key is entity type ("recipe", "inventory_item", etc.)
    # Value is the most recent entity of that type
    active_entities: dict[str, dict]  # EntityRef as dict
    
    # All entities from this conversation (for retrieval)
    # Key is entity ID, value is EntityRef
    all_entities: dict[str, dict]  # EntityRef as dict
    
    # Pending clarification/proposal from Think (for context threading)
    # When Think returns propose/clarify, this tracks what was asked
    # Next turn's Think can see user's response in context
    pending_clarification: dict[str, Any] | None  # {type, message, assumptions/questions}


# =============================================================================
# Graph State
# =============================================================================


class AlfredState(TypedDict, total=False):
    """
    Shared state passed through all LangGraph nodes.

    This is a TypedDict so LangGraph can properly type-check
    and merge state updates from each node.
    """

    # User context
    user_id: str
    conversation_id: str | None

    # Input
    user_message: str

    # Router output
    router_output: RouterOutput | None

    # Think output
    think_output: ThinkOutput | None

    # NOTE: Context is NOT pre-fetched. Act uses CRUD for all data access.
    # This field exists only for conversation context (Phase 5).
    context: dict[str, Any]

    # Act loop state
    current_step_index: int
    step_results: dict[int, Any]  # Cache of tool outputs by step index
    current_step_tool_results: list[Any]  # Tool results within current step (multi-tool pattern)
    current_subdomain: str | None  # Active subdomain for schema
    schema_requests: int  # Count of schema requests (for safeguard)
    pending_action: ActAction | None

    # Content archive (persists across turns for generate/analyze step results)
    # Keys: "turn_{turn_num}_step_{step_num}" or descriptive like "recipes_generated"
    # Allows Act to retrieve generated content from previous turns
    content_archive: dict[str, Any]

    # Step notes (CRUD steps leave notes for next step)
    prev_step_note: str | None  # Note from previous step for context
    
    # Within-turn entity tracking (IDs created this turn, for cross-step reference)
    # Accumulated as steps complete; merged into conversation.active_entities by Summarize
    turn_entities: list[dict]  # List of {type, id, label, step} dicts
    
    # Conversation context (Phase 5)
    conversation: ConversationContext

    # Final output
    final_response: str | None

    # Error state
    error: str | None
