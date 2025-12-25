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
    
    # Build the user prompt following: Task → Context → Instructions
    user_prompt = f"""## Task

**Goal**: {router_output.goal}

**User said**: "{state["user_message"]}"

**Agent**: {router_output.agent}

---

## Context

{context_section}

---

## Instructions

Create an execution plan. For each step, specify:
- `description`: What this step accomplishes
- `step_type`: crud, analyze, or generate
- `subdomain`: inventory, recipes, shopping, meal_plan, or preferences
- `complexity`: low, medium, or high"""

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
