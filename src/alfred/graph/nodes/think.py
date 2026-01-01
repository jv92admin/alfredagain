"""
Alfred V2 - Think Node.

The Think node creates an execution plan based on the goal.
It outputs steps with subdomain hints (not tool names).
NO data fetching - Act handles all data access via CRUD.

Now includes:
- Conversation context for multi-turn awareness
- User profile injection for personalized decision-making
- Kitchen dashboard for data availability awareness
- Subdomain dependencies for relationship understanding
- Clarify/Propose decision layer

Output: ThinkOutput with decision (plan_direct/propose/clarify) and steps or questions.
"""

from datetime import date
from pathlib import Path

from alfred.background.profile_builder import (
    format_dashboard_for_prompt,
    format_profile_for_prompt,
    get_cached_dashboard,
    get_cached_profile,
)
from alfred.graph.state import AlfredState, PlannedStep, ThinkOutput
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context
from alfred.tools.schema import get_complexity_rules, get_subdomain_dependencies_summary


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
    
    Now includes:
    - User profile for personalized decision-making
    - Kitchen dashboard for data availability awareness
    - Subdomain dependencies for relationship understanding
    - Clarify/Propose decision layer

    Args:
        state: Current graph state with router_output

    Returns:
        State update with think_output (decision + steps or questions)
    """
    router_output = state["router_output"]
    conversation = state.get("conversation", {})
    user_id = state.get("user_id")

    # Set node name for prompt logging
    set_current_node("think")

    if router_output is None:
        return {"error": "Router output missing"}

    # Format conversation context (condensed for Think)
    context_section = format_condensed_context(conversation)
    
    # Fetch user profile and kitchen dashboard for decision-making
    profile_section = ""
    dashboard_section = ""
    if user_id:
        try:
            profile = await get_cached_profile(user_id)
            profile_section = format_profile_for_prompt(profile)
        except Exception:
            pass  # Profile is optional
        
        try:
            dashboard = await get_cached_dashboard(user_id)
            dashboard_section = format_dashboard_for_prompt(dashboard)
        except Exception:
            pass  # Dashboard is optional
    
    # Get subdomain dependencies summary
    dependencies_section = get_subdomain_dependencies_summary()
    
    # Check for pending clarification from previous turn
    pending_clarification = conversation.get("pending_clarification")
    pending_section = ""
    if pending_clarification:
        pending_type = pending_clarification.get("type", "")
        if pending_type in ("propose", "clarify"):
            pending_section = f"""## Previous Turn

You asked for {'confirmation' if pending_type == 'propose' else 'clarification'}.
The user's current message is their response. Use this context to plan.

"""
    
    # Build the user prompt following: Task → Context → Instructions
    today = date.today().isoformat()
    
    user_prompt = f"""{pending_section}## Task

**Goal**: {router_output.goal}

**User said**: "{state["user_message"]}"

**Agent**: {router_output.agent}

**Today**: {today}

---

{profile_section}

{dashboard_section}

{dependencies_section}

---

## Conversation Context

{context_section}

---

## Instructions

Decide how to proceed:

1. **plan_direct** — Simple, unambiguous request. Create execution steps.
2. **propose** — Complex request, but you have enough context. State assumptions for user to confirm.
3. **clarify** — Missing critical context (empty profile, ambiguous intent). Ask focused questions.

**Default to PROPOSE when you have user profile/preferences.** Only CLARIFY if profile is empty or data is missing.

If plan_direct, include steps:
- `description`: What this step accomplishes
- `step_type`: crud, analyze, or generate
- `subdomain`: inventory, recipes, shopping, meal_plan, tasks, or preferences
- `complexity`: low, medium, or high"""

    # Call LLM for planning
    result = await call_llm(
        response_model=ThinkOutput,
        system_prompt=_get_system_prompt(),
        user_prompt=user_prompt,
        complexity=router_output.complexity,
    )

    # Apply automatic complexity escalation based on subdomain rules
    # (only for plan_direct with steps)
    if result.decision == "plan_direct" and result.steps:
        adjusted_steps = [adjust_step_complexity(step) for step in result.steps]
        result.steps = adjusted_steps

    return {
        "think_output": result,
        "current_step_index": 0,
        "step_results": {},
        "schema_requests": 0,
    }
