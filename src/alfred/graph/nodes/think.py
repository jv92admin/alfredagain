"""
Alfred V3 - Think Node.

The Think node creates an execution plan based on the goal.
It outputs steps with:
- subdomain hints (not tool names)
- step_type (read/analyze/generate/write)
- group field for parallelization

NO data fetching - Act handles all data access via CRUD.

V3 Changes:
- Steps include group field (same group = can run in parallel)
- Mode-aware planning depth
- Simplified step_types (read/analyze/generate/write)
- Proposal flow for complex Plan mode requests

Output: ThinkOutput with steps (including group) or proposal/clarification.
"""

from datetime import date
from pathlib import Path

from alfred.background.profile_builder import (
    format_dashboard_for_prompt,
    format_profile_for_prompt,
    get_cached_dashboard,
    get_cached_profile,
)
from alfred.core.entities import EntityRegistry
from alfred.core.modes import Mode, ModeContext
from alfred.graph.state import AlfredState, ThinkStep, ThinkOutput
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context
from alfred.tools.schema import get_complexity_rules


# Mutation verbs that trigger complexity escalation
MUTATION_VERBS = frozenset([
    "create", "save", "add", "update", "delete", "remove", 
    "insert", "modify", "generate", "write", "set", "change"
])


def adjust_step_complexity(step: ThinkStep) -> ThinkStep:
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
    
    # V3: step.complexity is a property derived from step_type
    # For now, we don't modify the step itself, but this could
    # be used for model selection hints in the future
    return step


def _get_mode_planning_guidance(mode: Mode) -> str:
    """Get planning guidance based on mode."""
    if mode == Mode.QUICK:
        return """**Mode: QUICK**
- Maximum 2 steps
- No proposal needed - execute directly
- Simple operations only"""
    elif mode == Mode.COOK:
        return """**Mode: COOK**
- Maximum 4 steps
- Focus on recipe operations
- Light proposal for complex requests"""
    elif mode == Mode.PLAN:
        return """**Mode: PLAN**
- Up to 8 steps for complex operations
- Propose for multi-step plans
- Full planning with parallelization"""
    else:  # CREATE
        return """**Mode: CREATE**
- Focus on generation steps
- Up to 4 steps
- Rich output, creative freedom"""


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
    Think node - creates execution plan with subdomain hints and groups.

    This node ONLY plans. It does NOT fetch data.
    Act node handles all data access via CRUD.
    
    V3 Features:
    - Steps include group field for parallelization
    - Mode-aware planning depth
    - Entity counts (not full data) for context
    - Simplified step_types: read/analyze/generate/write

    Args:
        state: Current graph state with router_output

    Returns:
        State update with think_output (steps with groups, or proposal/clarification)
    """
    router_output = state["router_output"]
    understand_output = state.get("understand_output")
    conversation = state.get("conversation", {})
    user_id = state.get("user_id")

    # Set node name for prompt logging
    set_current_node("think")

    if router_output is None:
        return {"error": "Router output missing"}
    
    # Use Understand's processed message if available (has resolved references)
    user_message = state["user_message"]
    processed_message = None
    referenced_entities = []
    if understand_output:
        processed_message = getattr(understand_output, "processed_message", None)
        referenced_entities = getattr(understand_output, "referenced_entities", []) or []

    # Get mode context
    mode_data = state.get("mode_context", {})
    mode_context = ModeContext.from_dict(mode_data) if mode_data else ModeContext.default()
    mode = mode_context.selected_mode
    mode_guidance = _get_mode_planning_guidance(mode)
    
    # Get entity counts (not full data)
    registry_data = state.get("entity_registry", {})
    entity_counts = {}
    if registry_data:
        registry = EntityRegistry.from_dict(registry_data)
        entity_counts = registry.get_counts_by_type()
    entity_counts_section = f"**Entity counts:** {entity_counts}" if entity_counts else ""

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
    
    # Note: Subdomain dependencies are now in prompts/think.md itself
    # Removed get_subdomain_dependencies_summary() to avoid duplication
    
    # Check for pending clarification/proposal from previous turn
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
    
    # Build task section with resolved info from Understand
    understand_section = ""
    if processed_message and processed_message != user_message:
        understand_section = f'\n**Resolved**: "{processed_message}"'
    if referenced_entities:
        understand_section += f"\n**Referenced entities**: {referenced_entities}"
    
    user_prompt = f"""{pending_section}## Task

**Goal**: {router_output.goal}

**User said**: "{user_message}"{understand_section}

**Agent**: {router_output.agent}

**Today**: {today}

{mode_guidance}

{entity_counts_section}

---

{profile_section}

{dashboard_section}

---

## Conversation Context

{context_section}

---

## Your Output

Return one of:
- `plan_direct` with steps (for clear, unambiguous requests)
- `propose` with proposal_message (for complex/exploratory requests)
- `clarify` with questions (only if truly missing critical context)

Each step needs: `description`, `step_type`, `subdomain`, `group`"""

    # Call LLM for planning
    result = await call_llm(
        response_model=ThinkOutput,
        system_prompt=_get_system_prompt(),
        user_prompt=user_prompt,
        complexity=router_output.complexity,
    )

    # Apply automatic complexity escalation based on subdomain rules
    if result.decision == "plan_direct" and result.steps:
        adjusted_steps = [adjust_step_complexity(step) for step in result.steps]
        result.steps = adjusted_steps

    return {
        "think_output": result,
        "current_step_index": 0,
        "step_results": {},
        "group_results": {},  # V3: track results by group
        "schema_requests": 0,
    }
