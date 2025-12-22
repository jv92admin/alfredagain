"""
Alfred V2 - Graph State Definition.

The AlfredState is the shared state passed through all nodes.
"""

from typing import Any, Literal, TypedDict

from pydantic import BaseModel


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

    type: str  # "ingredient", "recipe", "meal_plan", "pantry_item"
    id: str  # "ing_123", "rec_456"
    label: str  # "tomato" (human-readable for LLM context)
    source: str  # "db_lookup", "user_input", "generated"


# =============================================================================
# Core Contracts
# =============================================================================


class RouterOutput(BaseModel):
    """Output from the Router node."""

    agent: Literal["pantry", "coach", "cellar"]
    goal: str  # Natural language
    complexity: Literal["low", "medium", "high"]
    context_needs: list[str] = []  # ["inventory", "preferences", "recipes"]


class Step(BaseModel):
    """A single step in the execution plan."""

    name: str  # "Check pantry for missing ingredients"
    complexity: Literal["low", "medium", "high"] = "medium"


class ThinkOutput(BaseModel):
    """Output from the Think node."""

    goal: str
    steps: list[Step]


# =============================================================================
# Act Loop Actions
# =============================================================================


class ToolCallAction(BaseModel):
    """Request to call a tool."""

    action: Literal["tool_call"] = "tool_call"
    tool: str  # "find_ingredients", "add_to_inventory"
    arguments: dict[str, Any]  # Tool-specific args


class StepCompleteAction(BaseModel):
    """Indicates a step was completed successfully."""

    action: Literal["step_complete"] = "step_complete"
    step_name: str  # Which step was completed
    result_summary: str  # Brief description of outcome
    refs: list[EntityRef] = []  # Any entities created/modified


class AskUserAction(BaseModel):
    """Request clarification from the user."""

    action: Literal["ask_user"] = "ask_user"
    question: str  # Clear, single question
    context: str  # Why we need this info


class BlockedAction(BaseModel):
    """Indicates the agent is stuck and needs orchestrator intervention."""

    action: Literal["blocked"] = "blocked"
    reason_code: Literal[
        "INSUFFICIENT_INFORMATION",  # Need user input
        "PLAN_INVALID",  # Current plan won't work
        "TOOL_FAILURE",  # Tool returned error
        "AMBIGUOUS_INPUT",  # Multiple interpretations possible
    ]
    details: str  # Human-readable explanation
    suggested_next: Literal["ask_user", "replan", "fail"]


class FailAction(BaseModel):
    """Indicates unrecoverable failure."""

    action: Literal["fail"] = "fail"
    reason: str  # Why we can't proceed
    user_message: str  # What to tell the user


# Union type for all actions
ActAction = ToolCallAction | StepCompleteAction | AskUserAction | BlockedAction | FailAction


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

    # Retrieved context (from hybrid retrieval)
    context: dict[str, Any]

    # Act loop state
    current_step_index: int
    completed_steps: list[StepCompleteAction]
    pending_action: ActAction | None

    # Final output
    final_response: str | None

    # Error state
    error: str | None

