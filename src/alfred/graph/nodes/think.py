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
from alfred.prompts.injection import format_all_subdomain_guidance
from alfred.context.builders import build_think_context
from alfred.context.reasoning import (
    get_reasoning_trace,
    get_current_turn_curation,
    format_reasoning,
    format_curation_for_think,
)
from alfred.core.id_registry import SessionIdRegistry
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


# _format_entity_context_for_think() REMOVED (2026-01-23)
# Migrated to Context API: build_think_context() in context/builders.py
# Now uses ThinkContext.format_entity_context() with recipe detail tracking.


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
    
    # Get resolved references from Understand (V5: no processed_message, just refs)
    user_message = state["user_message"]
    referenced_entities = []
    if understand_output:
        referenced_entities = getattr(understand_output, "referenced_entities", []) or []

    # Build entity context using Context API (with recipe detail tracking)
    think_context = build_think_context(state)
    entity_context_section = think_context.format_entity_context()

    # Build entity counts from registry
    entity_counts_section = ""
    registry_data = state.get("id_registry")
    if registry_data:
        if isinstance(registry_data, SessionIdRegistry):
            registry = registry_data
        else:
            registry = SessionIdRegistry.from_dict(registry_data)
        entity_counts = {}
        for ref, entity_type in registry.ref_types.items():
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
        if entity_counts:
            entity_counts_section = f"**Entity counts:** {entity_counts}"

    # V6: Build reasoning trace section (Layer 3)
    reasoning_trace_section = ""
    reasoning_trace = get_reasoning_trace(conversation)
    if reasoning_trace.recent_summaries or reasoning_trace.reasoning_summary:
        reasoning_trace_section = format_reasoning(reasoning_trace, node="think")
    
    # V6: Get current turn's curation from Understand (same-turn context)
    curation_section = ""
    current_curation = get_current_turn_curation(state)
    if current_curation:
        curation_section = format_curation_for_think(current_curation)

    # Get mode context
    mode_data = state.get("mode_context", {})
    mode_context = ModeContext.from_dict(mode_data) if mode_data else ModeContext.default()
    mode = mode_context.selected_mode
    # Mode guidance now inline in Task section

    # Format conversation context (condensed for Think)
    context_section = format_condensed_context(conversation)
    
    # Fetch user profile and dashboard for decision-making
    profile_section = ""
    dashboard_section = ""
    subdomain_guidance_section = ""
    if user_id:
        try:
            profile = await get_cached_profile(user_id)
            profile_section = format_profile_for_prompt(profile)
            # Get subdomain guidance from profile (includes subdomain_guidance dict)
            if profile.subdomain_guidance:
                subdomain_guidance_section = format_all_subdomain_guidance(
                    {"subdomain_guidance": profile.subdomain_guidance}
                )
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
        if pending_type == "propose":
            proposal_goal = pending_clarification.get("goal", "")
            pending_section = f"""## ↑ Proposal Response

**You proposed:** {proposal_goal}
*(Full proposal in conversation above)*

**User is responding.** If they confirm → execute what you proposed.
If they modify → adjust the plan.

"""
        elif pending_type == "clarify":
            pending_section = """## ↑ Clarification Response

**You asked for more details** *(see conversation above)*

**User is answering.** Use their response to plan.

"""
    
    # Build user prompt as XML sections to fill placeholders in system prompt
    today = date.today().isoformat()
    
    # Build entities mentioned section
    understand_section = ""
    if referenced_entities:
        understand_section = f"\n**Entities mentioned**: {referenced_entities}"
    
    # Extract mode info
    mode_name = mode.name  # QUICK, PLAN, or CREATE
    max_steps = mode_context.max_steps
    
    # Build three XML sections that fill the placeholders
    
    # 1. Session Context (profile, dashboard, entities, reasoning trace)
    session_parts = []
    if profile_section:
        session_parts.append(profile_section)
    if subdomain_guidance_section:
        session_parts.append(subdomain_guidance_section)
    if dashboard_section:
        session_parts.append(dashboard_section)
    if entity_context_section:
        session_parts.append(entity_context_section)
    # V6: Add reasoning trace (what happened last turn)
    if reasoning_trace_section:
        session_parts.append(f"## What Happened Last Turn\n\n{reasoning_trace_section}")
    # V6: Add current turn's curation (Understand's decisions)
    if curation_section:
        session_parts.append(curation_section)
    
    session_context_content = "\n\n".join(session_parts) if session_parts else "*No session context available*"
    
    # 2. Conversation History (recent turns, pending clarification)
    conversation_parts = []
    if context_section:
        conversation_parts.append(context_section)
    if pending_section:
        conversation_parts.append(pending_section)
    
    conversation_content = "\n\n".join(conversation_parts) if conversation_parts else "*No conversation history*"
    
    # 3. Immediate Task (user message, today, mode, entity counts)
    immediate_task_content = f"""**User said**: "{user_message}"{understand_section}

**Today**: {today} | **Mode**: {mode_name} (max {max_steps} steps)

{entity_counts_section}"""
    
    # Assemble user prompt with XML sections
    user_prompt = f"""<session_context>
{session_context_content}
</session_context>

<conversation_history>
{conversation_content}
</conversation_history>

<immediate_task>
{immediate_task_content}
</immediate_task>"""

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
