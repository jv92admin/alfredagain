"""
Alfred V2 - Reply Node.

The Reply node synthesizes the final response to the user
based on execution results.
"""

from pathlib import Path

from pydantic import BaseModel

from alfred.graph.state import (
    AlfredState,
    AskUserAction,
    BlockedAction,
    FailAction,
)
from alfred.llm.client import call_llm


# Load prompts once at module level
_REPLY_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "reply.md"
_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "system.md"
_REPLY_PROMPT: str | None = None
_SYSTEM_PROMPT: str | None = None


def _get_prompts() -> tuple[str, str]:
    """Load the reply and system prompts."""
    global _REPLY_PROMPT, _SYSTEM_PROMPT
    
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    
    if _REPLY_PROMPT is None:
        _REPLY_PROMPT = _REPLY_PROMPT_PATH.read_text(encoding="utf-8")
    
    return _SYSTEM_PROMPT, _REPLY_PROMPT


class ReplyOutput(BaseModel):
    """The final response to the user."""
    
    response: str


async def reply_node(state: AlfredState) -> dict:
    """
    Reply node - generates final user response.
    
    Synthesizes execution results into a natural, helpful response.
    
    Args:
        state: Current graph state with completed_steps and any errors
        
    Returns:
        State update with final_response
    """
    system_prompt, reply_instructions = _get_prompts()
    
    # Combine system prompt with reply instructions
    full_system_prompt = f"{system_prompt}\n\n---\n\n{reply_instructions}"
    
    # Build context for the reply
    completed_steps = state.get("completed_steps", [])
    pending_action = state.get("pending_action")
    think_output = state.get("think_output")
    error = state.get("error")
    
    # Handle special cases
    if error:
        return {
            "final_response": f"I'm sorry, something went wrong: {error}"
        }
    
    # Handle ask_user - just pass through the question
    if isinstance(pending_action, AskUserAction):
        return {
            "final_response": f"{pending_action.question}\n\n({pending_action.context})"
        }
    
    # Handle fail
    if isinstance(pending_action, FailAction):
        return {
            "final_response": pending_action.user_message
        }
    
    # Handle blocked
    if isinstance(pending_action, BlockedAction):
        # Generate a helpful response about being blocked
        user_prompt = f"""## Situation
I was trying to help with: {think_output.goal if think_output else "the user's request"}

But I got stuck: {pending_action.details}

## What I Completed
{_format_completed_steps(completed_steps)}

Generate a helpful response explaining what happened and what we could try next."""

        result = await call_llm(
            response_model=ReplyOutput,
            system_prompt=full_system_prompt,
            user_prompt=user_prompt,
            complexity="low",
        )
        return {"final_response": result.response}
    
    # Normal completion - generate response from results
    user_prompt = f"""## Original Request
{state.get("user_message", "Unknown request")}

## Goal
{think_output.goal if think_output else "Complete the user's request"}

## What Was Done
{_format_completed_steps(completed_steps)}

Generate a natural, helpful response summarizing what was accomplished."""

    result = await call_llm(
        response_model=ReplyOutput,
        system_prompt=full_system_prompt,
        user_prompt=user_prompt,
        complexity="low",  # Reply generation is straightforward
    )
    
    return {"final_response": result.response}


def _format_completed_steps(completed_steps: list) -> str:
    """Format completed steps for the prompt."""
    if not completed_steps:
        return "No steps completed yet."
    
    lines = []
    for i, step in enumerate(completed_steps, 1):
        lines.append(f"{i}. **{step.step_name}**: {step.result_summary}")
        if step.refs:
            for ref in step.refs:
                lines.append(f"   - Created/Modified: {ref.label} ({ref.type})")
    
    return "\n".join(lines)

