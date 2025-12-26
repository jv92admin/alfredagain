"""
Alfred V2 - Think Node.

The Think node creates an execution plan based on the goal.
It outputs steps with subdomain hints (not tool names).
NO data fetching - Act handles all data access via CRUD.

Now includes conversation context for multi-turn awareness.
Applies automatic complexity escalation for linked-table operations.

Output: Steps with subdomain assignments for Act node to execute.
"""

from datetime import date
from pathlib import Path

from alfred.graph.state import AlfredState, PlannedStep, ThinkOutput
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context
from alfred.tools.schema import get_complexity_rules


# Mutation verbs that trigger complexity escalation
MUTATION_VERBS = frozenset([
    "create", "save", "add", "update", "delete", "remove", 
    "insert", "modify", "generate", "write", "set", "change"
])


def adjust_step_complexity(step: PlannedStep) -> PlannedStep:
    """
    Auto-escalate step complexity based on subdomain rules.
    
    Linked-table operations (e.g., recipes with recipe_ingredients)
    benefit from stronger models to handle parent-child patterns.
    
    Args:
        step: The planned step from LLM
        
    Returns:
        The step with potentially adjusted complexity
    """
    rules = get_complexity_rules(step.subdomain)
    if not rules:
        return step
    
    # Check if step description contains mutation verbs
    description_lower = step.description.lower()
    is_mutation = any(verb in description_lower for verb in MUTATION_VERBS)
    
    if is_mutation and rules.get("mutation"):
        # Only escalate if the rule is higher than current
        complexity_order = {"low": 0, "medium": 1, "high": 2}
        current_level = complexity_order.get(step.complexity, 0)
        rule_level = complexity_order.get(rules["mutation"], 0)
        
        if rule_level > current_level:
            step.complexity = rules["mutation"]
    
    elif not is_mutation and rules.get("read"):
        # Apply read complexity rule if present
        step.complexity = rules["read"]
    
    return step


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
    today = date.today().isoformat()
    
    user_prompt = f"""## Task

**Goal**: {router_output.goal}

**User said**: "{state["user_message"]}"

**Agent**: {router_output.agent}

**Today**: {today}

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

    # Apply automatic complexity escalation based on subdomain rules
    # (e.g., recipe mutations → high complexity for linked tables)
    adjusted_steps = [adjust_step_complexity(step) for step in result.steps]
    result.steps = adjusted_steps

    return {
        "think_output": result,
        "current_step_index": 0,
        "step_results": {},
        "schema_requests": 0,
    }
