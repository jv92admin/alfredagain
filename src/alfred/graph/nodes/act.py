"""
Alfred V2 - Act Node.

The Act node executes the plan step by step. It loops until:
- All steps complete (success)
- User input needed (ask_user)
- Unrecoverable error (fail)
- Agent handoff needed (call_agent - future)

Each iteration emits a structured action.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from alfred.graph.state import (
    ActAction,
    AlfredState,
    AskUserAction,
    BlockedAction,
    FailAction,
    StepCompleteAction,
    ToolCallAction,
)
from alfred.llm.client import call_llm_with_context


# =============================================================================
# Act Decision Model
# =============================================================================


class ActDecision(BaseModel):
    """
    The LLM's decision for what action to take.
    
    This is what we ask the LLM to produce. It then gets
    converted to the appropriate ActAction type.
    """

    action: str = Field(
        description="One of: tool_call, step_complete, ask_user, blocked, fail"
    )
    
    # For tool_call
    tool: str | None = Field(default=None, description="Tool name to call")
    arguments: dict[str, Any] | None = Field(default=None, description="Tool arguments")
    
    # For step_complete
    step_name: str | None = Field(default=None, description="Which step was completed")
    result_summary: str | None = Field(default=None, description="Brief outcome description")
    
    # For ask_user
    question: str | None = Field(default=None, description="Question to ask user")
    question_context: str | None = Field(default=None, description="Why we need this info")
    
    # For blocked
    reason_code: str | None = Field(default=None, description="INSUFFICIENT_INFORMATION, PLAN_INVALID, TOOL_FAILURE, AMBIGUOUS_INPUT")
    details: str | None = Field(default=None, description="Human-readable explanation")
    suggested_next: str | None = Field(default=None, description="ask_user, replan, fail")
    
    # For fail
    reason: str | None = Field(default=None, description="Why we can't proceed")
    user_message: str | None = Field(default=None, description="What to tell the user")


def _decision_to_action(decision: ActDecision) -> ActAction:
    """Convert LLM decision to typed action."""
    if decision.action == "tool_call":
        return ToolCallAction(
            tool=decision.tool or "unknown",
            arguments=decision.arguments or {},
        )
    elif decision.action == "step_complete":
        return StepCompleteAction(
            step_name=decision.step_name or "unknown",
            result_summary=decision.result_summary or "",
            refs=[],  # Tools would populate this
        )
    elif decision.action == "ask_user":
        return AskUserAction(
            question=decision.question or "Could you clarify?",
            context=decision.question_context or "",
        )
    elif decision.action == "blocked":
        return BlockedAction(
            reason_code=decision.reason_code or "AMBIGUOUS_INPUT",  # type: ignore
            details=decision.details or "Unable to proceed",
            suggested_next=decision.suggested_next or "ask_user",  # type: ignore
        )
    else:  # fail
        return FailAction(
            reason=decision.reason or "Unknown error",
            user_message=decision.user_message or "I'm sorry, I couldn't complete that request.",
        )


# =============================================================================
# Act Node
# =============================================================================

# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "act.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    """Load the act system prompt."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


async def act_node(state: AlfredState) -> dict:
    """
    Act node - executes one step of the plan.
    
    This is called repeatedly by the graph until a terminal condition.
    
    Args:
        state: Current graph state with think_output and current_step_index
        
    Returns:
        State update with action result
    """
    think_output = state.get("think_output")
    current_step_index = state.get("current_step_index", 0)
    completed_steps = state.get("completed_steps", [])
    context = state.get("context", {})
    
    if think_output is None:
        return {
            "pending_action": FailAction(
                reason="No plan available",
                user_message="I'm sorry, I couldn't create a plan for that request.",
            ),
        }
    
    steps = think_output.steps
    
    # Check if all steps are done
    if current_step_index >= len(steps):
        return {
            "pending_action": None,  # Signal completion
        }
    
    current_step = steps[current_step_index]
    
    # Build prompt for LLM
    completed_summary = "\n".join(
        f"- {s.step_name}: {s.result_summary}" for s in completed_steps
    ) if completed_steps else "None yet"
    
    user_prompt = f"""## Current Step
Step {current_step_index + 1} of {len(steps)}: {current_step.name}
Complexity: {current_step.complexity}

## Completed Steps
{completed_summary}

## Original Goal
{think_output.goal}

## Original User Message
{state.get("user_message", "")}

Decide what action to take for the current step."""

    # Call LLM for decision
    decision = await call_llm_with_context(
        response_model=ActDecision,
        system_prompt=_get_system_prompt(),
        user_prompt=user_prompt,
        context=context,
        complexity=current_step.complexity,
    )
    
    action = _decision_to_action(decision)
    
    # Handle step_complete - advance to next step
    if isinstance(action, StepCompleteAction):
        return {
            "pending_action": action,
            "current_step_index": current_step_index + 1,
            "completed_steps": completed_steps + [action],
        }
    
    # Other actions don't advance the step
    return {
        "pending_action": action,
    }


def should_continue_act(state: AlfredState) -> str:
    """
    Determine if ACT loop should continue or exit.
    
    Returns:
        - "continue" to loop back to act
        - "reply" to move to reply node
        - "ask_user" to pause for user input
        - "fail" to exit with error
    """
    pending_action = state.get("pending_action")
    think_output = state.get("think_output")
    current_step_index = state.get("current_step_index", 0)
    
    # No action = all steps complete
    if pending_action is None:
        return "reply"
    
    # Check action type
    if isinstance(pending_action, StepCompleteAction):
        # Check if more steps remain
        if think_output and current_step_index < len(think_output.steps):
            return "continue"
        return "reply"
    
    if isinstance(pending_action, ToolCallAction):
        # After tool execution, continue the loop
        # (Tool execution happens in a separate node in full implementation)
        return "continue"
    
    if isinstance(pending_action, AskUserAction):
        return "ask_user"
    
    if isinstance(pending_action, BlockedAction):
        # For now, treat blocked as needing reply
        # Full implementation would handle replan vs ask_user vs fail
        return "reply"
    
    if isinstance(pending_action, FailAction):
        return "fail"
    
    return "reply"

