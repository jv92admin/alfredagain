"""
Alfred V2 - Think Node.

The Think node creates an execution plan based on the goal and context.
It breaks down the task into discrete steps with complexity ratings.
"""

from pathlib import Path

from alfred.db.context import get_context
from alfred.graph.state import AlfredState, ThinkOutput
from alfred.llm.client import call_llm_with_context


# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "think.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    """Load the think system prompt."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


async def think_node(state: AlfredState) -> dict:
    """
    Think node - creates execution plan.

    Uses the router output to understand what agent and goal,
    retrieves necessary context, and generates steps.

    Args:
        state: Current graph state with router_output

    Returns:
        State update with think_output and context
    """
    router_output = state["router_output"]
    user_id = state["user_id"]

    if router_output is None:
        return {"error": "Router output missing"}

    # Retrieve context based on router's context_needs
    context = await get_context(
        user_id=user_id,
        needs=router_output.context_needs,
        query=router_output.goal,
    )

    # Build the user prompt with goal
    user_prompt = f"""## Goal
{router_output.goal}

## Agent
{router_output.agent}

## User Request
{state["user_message"]}

Create an execution plan for this goal."""

    # Call LLM for planning
    # Use the router's complexity assessment
    result = await call_llm_with_context(
        response_model=ThinkOutput,
        system_prompt=_get_system_prompt(),
        user_prompt=user_prompt,
        context=context,
        complexity=router_output.complexity,
    )

    return {
        "think_output": result,
        "context": context,
        "current_step_index": 0,
        "completed_steps": [],
    }

