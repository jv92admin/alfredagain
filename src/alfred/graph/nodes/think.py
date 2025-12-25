"""
Alfred V2 - Think Node.

The Think node creates an execution plan based on the goal.
It outputs steps with subdomain hints (not tool names).
NO data fetching - Act handles all data access via CRUD.

Now includes conversation context for multi-turn awareness.

Output: Steps with subdomain assignments for Act node to execute.
"""

from pathlib import Path

from alfred.graph.state import AlfredState, ThinkOutput
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context


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
    Think node - creates execution plan with subdomain hints.

    This node ONLY plans. It does NOT fetch data.
    Act node handles all data access via CRUD.
    Now includes condensed conversation context for multi-turn awareness.

    Args:
        state: Current graph state with router_output

    Returns:
        State update with think_output (steps with subdomain hints)
    """
    router_output = state["router_output"]
    conversation = state.get("conversation", {})

    # Set node name for prompt logging
    set_current_node("think")

    if router_output is None:
        return {"error": "Router output missing"}

    # Format conversation context (condensed for Think)
    context_section = format_condensed_context(conversation)
    
    # Build the user prompt with goal and context
    user_prompt = f"""## Goal
{router_output.goal}

## Agent
{router_output.agent}

## User Request
{state["user_message"]}

## Conversation Context
{context_section}

---

Create an execution plan for this goal. For each step:
1. Write a clear description of what needs to be done
2. Assign the appropriate subdomain (inventory, recipes, shopping, meal_plan, preferences)
3. Set the complexity (low, medium, high)

The Act node will receive the table schema for each step's subdomain and execute CRUD operations."""

    # Call LLM for planning
    result = await call_llm(
        response_model=ThinkOutput,
        system_prompt=_get_system_prompt(),
        user_prompt=user_prompt,
        complexity=router_output.complexity,
    )

    return {
        "think_output": result,
        "current_step_index": 0,
        "step_results": {},
        "schema_requests": 0,
    }
