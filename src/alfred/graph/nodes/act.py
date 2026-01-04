"""
Alfred V3 - Act Node.

The Act node executes the plan step by step using generic CRUD tools.
For each step, it:
1. Gets step_type-specific prompt sections via injection.py
2. Decides which CRUD operation to perform (for read/write steps)
3. Executes and caches the result
4. Tags entities at creation for lifecycle tracking

V3 Changes:
- Step-type-specific prompts (read/analyze/generate/write)
- Entity tagging at creation (pending/active states)
- Group-based results for parallelization
- Mode-aware prompt verbosity

V3.1 Changes:
- Group parallelization: steps in same group run concurrently
- Parallel execution uses asyncio.gather for wall-clock speedup

Each iteration emits a structured action.
"""

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from alfred.core.entities import Entity, EntityState
from alfred.core.modes import Mode, ModeContext
from alfred.graph.state import (
    ACT_CONTEXT_THRESHOLD,
    FULL_DETAIL_STEPS,
    ActAction,
    AlfredState,
    AskUserAction,
    BlockedAction,
    FailAction,
    ThinkStep,
    RequestSchemaAction,
    RetrieveStepAction,
    StepCompleteAction,
    ToolCallAction,
)
from alfred.background.profile_builder import format_profile_for_prompt, get_cached_profile
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_full_context
from alfred.prompts.injection import build_act_prompt, build_act_quick_prompt
from alfred.tools.crud import execute_crud
from alfred.tools.schema import get_schema_with_fallback
from alfred.prompts.personas import get_full_subdomain_content
from alfred.prompts.examples import get_contextual_examples

# Entity types to track across steps
TRACKED_ENTITY_TYPES = {"recipes", "meal_plans", "tasks", "recipe", "meal_plan", "task"}


def _extract_turn_entities(
    step_data: Any, 
    step_index: int, 
    step_type: str,
    current_turn: int,
) -> list[Entity]:
    """
    Extract and tag entities from step results for lifecycle tracking.
    
    V3: Returns Entity objects with proper state tagging:
    - db_read results → state=active (from DB, already exists)
    - generate results → state=pending (awaiting confirmation)
    - write results → state=pending (until confirmed)
    """
    entities: list[Entity] = []
    
    # Determine source and state based on step_type
    if step_type == "read":
        source = "db_read"
        default_state = EntityState.ACTIVE
    elif step_type == "generate":
        source = "generate"
        default_state = EntityState.PENDING
    elif step_type == "write":
        source = "db_write"
        default_state = EntityState.PENDING  # Until user confirms
    else:  # analyze
        source = "analyze"
        default_state = EntityState.PENDING
    
    def extract_from_record(record: dict, table: str | None = None) -> None:
        if not isinstance(record, dict):
            return
        
        # Get ID (could be real UUID or temp_id)
        record_id = record.get("id") or record.get("temp_id")
        if not record_id:
            return
            
        # Infer table/type from record if not provided
        entity_type = table
        if entity_type is None:
            if "recipe_id" in record or "instructions" in record:
                entity_type = "recipe"
            elif "meal_type" in record and "date" in record:
                entity_type = "meal_plan"
            elif "title" in record and ("due_date" in record or "category" in record):
                entity_type = "task"
            elif record.get("type"):
                entity_type = record["type"]
        
        # Normalize table names to entity types
        if entity_type == "recipes":
            entity_type = "recipe"
        elif entity_type == "meal_plans":
            entity_type = "meal_plan"
        elif entity_type == "tasks":
            entity_type = "task"
        
        if entity_type:
            # Determine state from record if specified
            state = default_state
            if "state" in record:
                try:
                    state = EntityState(record["state"])
                except ValueError:
                    pass
            
            entity = Entity(
                id=str(record_id),
                type=entity_type,
                label=record.get("name") or record.get("title") or record.get("label") or str(record_id)[:8],
                state=state,
                source=source,
                turn_created=current_turn,
                turn_last_ref=current_turn,
                subdomain=table,
                data=record if step_type == "generate" else None,  # Keep full data for generated content
            )
            entities.append(entity)
    
    def process_item(item: Any, table: str | None = None) -> None:
        if isinstance(item, dict):
            if "id" in item or "temp_id" in item:
                extract_from_record(item, table)
            else:
                # Check for nested collections like {"recipes": [...]}
                for key, val in item.items():
                    if isinstance(val, list):
                        for v in val:
                            process_item(v, key)
                    elif isinstance(val, dict):
                        process_item(val, key)
        elif isinstance(item, list):
            for v in item:
                process_item(v, table)
    
    # Handle tuple format from CRUD: [(tool, table, result), ...]
    if isinstance(step_data, list):
        for item in step_data:
            if isinstance(item, tuple) and len(item) >= 2:
                if len(item) == 3:
                    _tool, table, result = item
                    process_item(result, table)
                else:
                    _tool, result = item
                    process_item(result)
            else:
                process_item(item)
    else:
        process_item(step_data)
    
    return entities


def _format_turn_entities(turn_entities: list[Entity | dict]) -> str:
    """Format accumulated turn entities for Act's prompt."""
    if not turn_entities:
        return ""
    
    lines = ["### Entities Created This Turn (use these IDs for linking)"]
    
    # Group by type for readability
    by_type: dict[str, list[dict]] = {}
    for e in turn_entities:
        # Handle both Entity objects and dicts
        if isinstance(e, Entity):
            etype = e.type
            ref = {"id": e.id, "label": e.label, "state": e.state.value}
        else:
            etype = e.get("type", "unknown")
            ref = e
        
        if etype not in by_type:
            by_type[etype] = []
        by_type[etype].append(ref)
    
    for etype, ents in by_type.items():
        lines.append(f"**{etype}:**")
        for e in ents:
            state_badge = f" [{e.get('state', 'active')}]" if e.get('state') else ""
            lines.append(f"  - `{e['id']}` — {e.get('label', 'unnamed')}{state_badge}")
    
    return "\n".join(lines)


# =============================================================================
# Param Validation (catch LLM hallucinations before Pydantic)
# =============================================================================


def _fix_and_validate_tool_params(tool: str, params: dict) -> tuple[dict, str | None]:
    """
    Fix common LLM hallucinations and validate tool params.
    
    Returns (fixed_params, error_message).
    - If fixable: returns (fixed_params, None)
    - If unfixable: returns (original_params, error_message)
    
    Common patterns fixed:
    - "limit" or "columns" strings accidentally put in filters array
    """
    if not isinstance(params, dict):
        return params, f"params must be a dict, got {type(params).__name__}"
    
    # Make a copy to fix
    fixed = dict(params)
    
    # Fix filters array - remove misplaced strings like "limit", "columns"
    if "filters" in fixed:
        filters = fixed["filters"]
        # Auto-fix: empty dict {} → empty list [] (common LLM confusion)
        if isinstance(filters, dict) and len(filters) == 0:
            fixed["filters"] = []
            filters = []
        elif not isinstance(filters, list):
            return params, f"filters must be a list, got {type(filters).__name__}"
        
        # Extract valid filter dicts, log what we removed
        valid_filters = []
        removed_items = []
        for i, f in enumerate(filters):
            if isinstance(f, dict) and "field" in f and "op" in f:
                valid_filters.append(f)
            else:
                removed_items.append(repr(f)[:30])
        
        if removed_items:
            # Auto-fix by keeping only valid filters
            fixed["filters"] = valid_filters
            # Log what we fixed (but don't fail)
            import logging
            logging.getLogger("alfred.act").warning(
                f"Auto-fixed malformed filters: removed {removed_items}"
            )
    
    # Fix or_filters similarly
    if "or_filters" in fixed:
        or_filters = fixed["or_filters"]
        # Auto-fix: empty dict {} → empty list []
        if isinstance(or_filters, dict) and len(or_filters) == 0:
            fixed["or_filters"] = []
            or_filters = []
        elif not isinstance(or_filters, list):
            return params, f"or_filters must be a list, got {type(or_filters).__name__}"
        
        valid_or_filters = []
        for f in or_filters:
            if isinstance(f, dict) and "field" in f and "op" in f:
                valid_or_filters.append(f)
        fixed["or_filters"] = valid_or_filters
    
    # Validate data for create/update (can't auto-fix these)
    if tool in ("db_create", "db_update") and "data" in fixed:
        data = fixed["data"]
        if tool == "db_update":
            if not isinstance(data, dict):
                return params, f"db_update data must be a dict, got {type(data).__name__}"
        elif tool == "db_create":
            if not isinstance(data, (dict, list)):
                return params, f"db_create data must be dict or list, got {type(data).__name__}"
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if not isinstance(item, dict):
                        return params, f"db_create data[{i}] must be a dict, got {type(item).__name__}"
    
    return fixed, None


# =============================================================================
# Group Parallelization Helpers
# =============================================================================


def _group_steps_by_group(steps: list) -> dict[int, list[tuple[int, Any]]]:
    """
    Group steps by their group field.
    
    Returns dict: {group_num: [(step_index, step), ...]}
    """
    groups: dict[int, list[tuple[int, Any]]] = {}
    for idx, step in enumerate(steps):
        group_num = getattr(step, "group", 0)
        if group_num not in groups:
            groups[group_num] = []
        groups[group_num].append((idx, step))
    return groups


def _get_current_group(steps: list, current_step_index: int) -> int:
    """Get the group number for the current step."""
    if current_step_index >= len(steps):
        return -1
    return getattr(steps[current_step_index], "group", 0)


def _get_steps_in_group(steps: list, group_num: int) -> list[tuple[int, Any]]:
    """Get all (step_index, step) tuples for a given group."""
    return [
        (idx, step) for idx, step in enumerate(steps)
        if getattr(step, "group", 0) == group_num
    ]


def _is_first_step_in_group(steps: list, step_index: int) -> bool:
    """Check if this step is the first in its group."""
    if step_index >= len(steps):
        return False
    current_group = getattr(steps[step_index], "group", 0)
    # Check if any previous step has the same group
    for i in range(step_index):
        if getattr(steps[i], "group", 0) == current_group:
            return False
    return True


# =============================================================================
# Act Decision Model
# =============================================================================


class ActDecision(BaseModel):
    """
    The LLM's decision for what action to take.

    This is what we ask the LLM to produce.
    """

    action: Literal[
        "tool_call", "step_complete", "request_schema", "retrieve_step", "retrieve_archive", "ask_user", "blocked", "fail"
    ] = Field(description="The action to take")

    # For tool_call
    tool: Literal["db_read", "db_create", "db_update", "db_delete"] | None = Field(
        default=None, description="CRUD tool to call"
    )
    params: dict[str, Any] | None = Field(default=None, description="Tool parameters")

    # For step_complete
    result_summary: str | None = Field(
        default=None, description="Brief outcome description"
    )
    data: Any | None = Field(default=None, description="Full result data for caching")
    note_for_next_step: str | None = Field(
        default=None, description="Short note for next step (IDs, counts, key info)"
    )

    # For request_schema
    subdomain: str | None = Field(
        default=None, description="Subdomain to request schema for"
    )
    
    # For retrieve_step (fetch older step data)
    step_index: int | None = Field(
        default=None, description="Index of the step to retrieve (0-based)"
    )
    
    # For retrieve_archive (fetch generated content from previous turns)
    archive_key: str | None = Field(
        default=None, description="Key of archived content to retrieve (e.g., 'generated_recipes')"
    )

    # For ask_user
    question: str | None = Field(default=None, description="Question to ask user")
    context: str | None = Field(default=None, description="Why we need this info")

    # For blocked
    reason_code: Literal["INSUFFICIENT_INFO", "PLAN_INVALID", "TOOL_FAILURE"] | None = (
        Field(default=None, description="Blocked reason")
    )
    details: str | None = Field(default=None, description="Human-readable explanation")
    suggested_next: Literal["ask_user", "replan", "fail"] | None = Field(
        default=None, description="Suggested next action"
    )

    # For fail
    reason: str | None = Field(default=None, description="Why we can't proceed")
    user_message: str | None = Field(
        default=None, description="What to tell the user"
    )


def _decision_to_action(decision: ActDecision) -> ActAction:
    """Convert LLM decision to typed action."""
    match decision.action:
        case "tool_call":
            return ToolCallAction(
                tool=decision.tool or "db_read",
                params=decision.params or {},
            )
        case "step_complete":
            return StepCompleteAction(
                result_summary=decision.result_summary or "",
                data=decision.data,
            )
        case "request_schema":
            return RequestSchemaAction(
                subdomain=decision.subdomain or "inventory",
            )
        case "ask_user":
            return AskUserAction(
                question=decision.question or "Could you clarify?",
                context=decision.context or "",
            )
        case "blocked":
            return BlockedAction(
                reason_code=decision.reason_code or "PLAN_INVALID",
                details=decision.details or "Unable to proceed",
                suggested_next=decision.suggested_next or "ask_user",
            )
        case "fail":
            return FailAction(
                reason=decision.reason or "Unknown error",
                user_message=decision.user_message
                or "I'm sorry, I couldn't complete that request.",
            )
        case _:
            return FailAction(
                reason=f"Unknown action: {decision.action}",
                user_message="I encountered an unexpected error.",
            )


# =============================================================================
# Act Node
# =============================================================================

# Prompt paths
_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "act"

# Cache for loaded prompts
_PROMPT_CACHE: dict[str, str] = {}


def _load_prompt(filename: str) -> str:
    """Load a prompt file from prompts/act/ directory."""
    if filename not in _PROMPT_CACHE:
        path = _PROMPTS_DIR / filename
        if path.exists():
            _PROMPT_CACHE[filename] = path.read_text(encoding="utf-8")
        else:
            _PROMPT_CACHE[filename] = ""
    return _PROMPT_CACHE[filename]


def _get_system_prompt(step_type: str = "read") -> str:
    """
    Build the Act system prompt from layers.
    
    Layers:
    1. base.md - Universal role, principles, exit contract (NO tools)
    2. crud.md - Tools, filters, operators (only for read/write)
    3. {step_type}.md - Mechanics for this step type
    
    Subdomain content is added to user_prompt, not system_prompt.
    """
    base = _load_prompt("base.md")
    step_type_content = _load_prompt(f"{step_type}.md")
    
    # CRUD steps need the tools reference
    if step_type in ("read", "write"):
        crud = _load_prompt("crud.md")
        parts = [base]
        if crud:
            parts.append(crud)
        if step_type_content:
            parts.append(step_type_content)
        return "\n\n---\n\n".join(parts)
    
    # Generate/analyze don't need CRUD tools
    if step_type_content:
        return f"{base}\n\n---\n\n{step_type_content}"
    return base


def _format_step_results(step_results: dict[int, Any], current_index: int) -> str:
    """Format previous step results for context.
    
    Last FULL_DETAIL_STEPS get FULL data (essential for analyze steps).
    Older steps get summarized.
    
    Uses table-aware formatting to reduce token bloat while preserving
    the critical info (IDs, names) that Act needs for subsequent steps.
    """
    from alfred.prompts.injection import _format_records_for_table, _infer_table_from_record
    
    if not step_results:
        return "### Previous Step Results\n*No previous steps completed yet.*"

    lines = ["### Previous Step Results", ""]
    
    # Determine which steps get full detail
    max_step = max(step_results.keys()) if step_results else -1
    full_detail_threshold = max_step - FULL_DETAIL_STEPS + 1  # Last N steps get full detail

    for idx in sorted(step_results.keys()):
        result = step_results[idx]
        step_num = idx + 1
        is_recent = idx >= full_detail_threshold
        
        # Parse result format: [(tool_name, subdomain, result_data), ...]
        if isinstance(result, list) and result and isinstance(result[0], tuple):
            for tool_call in result:
                if len(tool_call) >= 3:
                    tool_name, subdomain, data = tool_call[:3]
                    # Map subdomain to table (they usually match)
                    table = _subdomain_to_table(subdomain)
                    lines.append(f"**Step {step_num}** [{tool_name}] on `{table}`:")
                    
                    if is_recent:
                        # Full detail with clean formatting
                        lines.extend(_format_step_data_clean(data, table))
                    else:
                        # Summarized for older steps
                        lines.append(_summarize_step_data(data, table))
        elif isinstance(result, list):
            # Direct list (legacy format)
            table = _infer_table_from_record(result[0]) if result else None
            lines.append(f"**Step {step_num}** ({len(result)} records):")
            if is_recent:
                lines.extend(_format_step_data_clean(result, table))
            else:
                lines.append(f"  {len(result)} records")
        elif isinstance(result, int):
            lines.append(f"**Step {step_num}**: Affected {result} records")
        else:
            lines.append(f"**Step {step_num}**: (use retrieve_step for details)")
        
        lines.append("")

    return "\n".join(lines)


def _subdomain_to_table(subdomain: str) -> str:
    """Map subdomain to primary table name."""
    mapping = {
        "inventory": "inventory",
        "shopping": "shopping_list",
        "recipes": "recipes",
        "meal_plans": "meal_plans",
        "tasks": "tasks",
        "preferences": "preferences",
    }
    return mapping.get(subdomain, subdomain)


def _format_step_data_clean(data: Any, table: str | None) -> list[str]:
    """Format step data in clean, readable format with IDs preserved."""
    from alfred.prompts.injection import _format_records_for_table
    
    if isinstance(data, list):
        if not data:
            return ["  (no records)"]
        formatted = _format_records_for_table(data, table)
        # Add a summary line with all IDs for easy copy-paste
        ids = [str(r.get("id"))[-8:] for r in data if isinstance(r, dict) and r.get("id")]
        if ids:
            formatted.append(f"  **IDs (short):** {', '.join(ids)}")
        return formatted
    elif isinstance(data, int):
        return [f"  Affected {data} records"]
    elif isinstance(data, dict):
        from alfred.prompts.injection import _format_record_clean
        return [_format_record_clean(data, table)]
    else:
        return [f"  {str(data)[:200]}"]


def _summarize_step_data(data: Any, table: str | None) -> str:
    """Summarize older step data compactly."""
    if isinstance(data, list):
        if not data:
            return "  (no records)"
        count = len(data)
        # Just show names if available
        names = [r.get("name") or r.get("title") for r in data[:3] if isinstance(r, dict)]
        names = [n for n in names if n]
        if names:
            preview = ", ".join(names[:3])
            return f"  {count} records: {preview}{'...' if count > 3 else ''}"
        return f"  {count} records"
    elif isinstance(data, int):
        return f"  Affected {data} records"
    else:
        return "  (data available via retrieve_step)"


def _extract_key_fields(records: list[dict]) -> str:
    """Extract key identifiers from db_read results for quick reference."""
    if not records:
        return ""
    
    # Try to find id and name fields
    first = records[0]
    has_id = "id" in first
    has_name = "name" in first
    
    if not has_id and not has_name:
        return ""
    
    lines = ["**Quick Reference (IDs for next query):**"]
    for r in records:
        parts = []
        if has_id:
            parts.append(f"`{r.get('id')}`")
        if has_name:
            parts.append(r.get('name', ''))
        lines.append(f"- {' — '.join(parts)}")
    
    return "\n".join(lines)


def _format_current_step_results(tool_results: list[tuple], tool_calls_made: int) -> str:
    """Format tool results from current step - show ACTUAL data with clean formatting."""
    from alfred.prompts.injection import _format_records_for_table, _infer_table_from_record
    
    if not tool_results:
        return ""
    
    lines = [f"## What Already Happened This Step ({tool_calls_made} tool calls)", ""]
    
    for i, item in enumerate(tool_results, 1):
        # Handle both (tool, table, result) and (tool, result) formats
        if len(item) == 3:
            tool_name, subdomain, result = item
            table = _subdomain_to_table(subdomain) if subdomain else None
        else:
            tool_name, result = item
            table = None
        
        # Infer table from data if not provided
        if not table and isinstance(result, list) and result:
            table = _infer_table_from_record(result[0])
        
        table_label = f" on `{table}`" if table else ""
        lines.append(f"### Tool Call {i}: `{tool_name}`{table_label}")
        
        # Show result with semantic meaning
        if tool_name == "db_read":
            if isinstance(result, list):
                if len(result) == 0:
                    lines.append("**Result: 0 records found.**")
                    lines.append("→ Empty result. If step goal is READ: this is your answer. If step goal is ADD/CREATE: proceed with db_create.")
                else:
                    lines.append(f"**Result: {len(result)} records found:**")
                    # Clean formatted records with IDs visible
                    formatted = _format_records_for_table(result[:50], table)
                    lines.extend(formatted)
                    if len(result) > 50:
                        lines.append(f"  ... and {len(result) - 50} more")
                    # Summary of all IDs for easy use in next query
                    ids = [str(r.get("id")) for r in result if isinstance(r, dict) and r.get("id")]
                    if ids:
                        lines.append("")
                        lines.append(f"**All IDs ({len(ids)}):** Use these in `in` filter for next step")
                        # Show full IDs for copy-paste (these are what Act needs)
                        lines.append(f"```\n{ids}\n```")
            else:
                lines.append(f"Result: `{result}`")
        elif tool_name == "db_create":
            if isinstance(result, list):
                lines.append(f"**✓ Created {len(result)} records:**")
                formatted = _format_records_for_table(result, table)
                lines.extend(formatted)
                # Show IDs created
                ids = [str(r.get("id")) for r in result if isinstance(r, dict) and r.get("id")]
                if ids:
                    lines.append(f"**Created IDs:** {ids}")
            elif isinstance(result, dict):
                lines.append(f"**✓ Created 1 record:**")
                from alfred.prompts.injection import _format_record_clean
                lines.append(_format_record_clean(result, table))
            else:
                lines.append(f"**✓ Created:** `{result}`")
        elif tool_name == "db_update":
            if isinstance(result, list):
                lines.append(f"**✓ Updated {len(result)} records**")
            elif isinstance(result, dict):
                lines.append(f"**✓ Updated 1 record**")
            else:
                lines.append(f"**✓ Updated:** `{result}`")
        elif tool_name == "db_delete":
            if isinstance(result, list):
                lines.append(f"**✓ Deleted {len(result)} records**")
            elif isinstance(result, int):
                lines.append(f"**✓ Deleted {result} records**")
            else:
                lines.append(f"**✓ Deleted:** `{result}`")
        else:
            # Generic fallback
            import json
            if isinstance(result, (dict, list)):
                result_json = json.dumps(result, indent=2, default=str)
                if len(result_json) > 2000:
                    lines.append("```json")
                    lines.append(result_json[:2000] + "\n... (truncated)")
                    lines.append("```")
                else:
                    lines.append("```json")
                    lines.append(result_json)
                    lines.append("```")
            else:
                lines.append(f"Result: `{result}`")
        
        lines.append("")
    
    # NOTE: Decision prompt moved to END of user prompt (not buried here in section 2)
    
    return "\n".join(lines)


# Maximum tool calls allowed within a single step (circuit breaker)
# 3 is enough for: read main → read related → complete (or retry once)
MAX_TOOL_CALLS_PER_STEP = 3


async def act_node(state: AlfredState) -> dict:
    """
    Act node - executes one step of the plan using CRUD tools.

    For each step:
    1. Gets schema for the step's subdomain
    2. Shows previous step results + current step's tool results
    3. LLM decides CRUD operation or step_complete
    4. Execute and cache result, loop back for more tool calls
    5. Only advance step when LLM says step_complete

    This enables multi-tool-call patterns within a single step
    (e.g., create recipe, then create each recipe_ingredient).

    Now includes full conversation context (last 2 turns/steps in full detail).
    Circuit breaker: Max 5 tool calls per step to prevent infinite loops.

    Args:
        state: Current graph state with think_output and current_step_index

    Returns:
        State update with action result
    """
    think_output = state.get("think_output")
    current_step_index = state.get("current_step_index", 0)
    step_results = state.get("step_results", {})
    current_step_tool_results = state.get("current_step_tool_results", [])
    user_id = state.get("user_id", "")
    schema_requests = state.get("schema_requests", 0)
    conversation = state.get("conversation", {})
    prev_step_note = state.get("prev_step_note")
    
    # Circuit breaker - force step_complete if too many tool calls
    if len(current_step_tool_results) >= MAX_TOOL_CALLS_PER_STEP:
        # Force step completion with whatever we have
        step_data = current_step_tool_results if current_step_tool_results else None
        new_step_results = step_results.copy()
        new_step_results[current_step_index] = step_data
        
        return {
            "pending_action": StepCompleteAction(
                result_summary=f"Step completed (max {MAX_TOOL_CALLS_PER_STEP} tool calls reached)",
                data=step_data,
            ),
            "current_step_index": current_step_index + 1,
            "step_results": new_step_results,
            "current_step_tool_results": [],
            "schema_requests": 0,
        }
    
    # Duplicate empty query detection - if same table returned empty twice, force completion
    if len(current_step_tool_results) >= 2:
        empty_tables = set()
        for item in current_step_tool_results:
            if len(item) >= 3:
                tool_name, table, result = item[0], item[1], item[2]
                if tool_name == "db_read" and (result == [] or result is None):
                    if table in empty_tables:
                        # Same table queried twice with empty results - stop retrying
                        logger.info(f"Act: Duplicate empty query on {table}, forcing step completion")
                        step_data = current_step_tool_results
                        new_step_results = step_results.copy()
                        new_step_results[current_step_index] = step_data
                        return {
                            "pending_action": StepCompleteAction(
                                result_summary=f"Step completed (no data found in {table})",
                                data=step_data,
                            ),
                            "current_step_index": current_step_index + 1,
                            "step_results": new_step_results,
                            "current_step_tool_results": [],
                            "schema_requests": 0,
                        }
                    empty_tables.add(table)

    # Set node name for prompt logging
    set_current_node("act")

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

    current_step: ThinkStep = steps[current_step_index]  # type: ignore

    # Get step type (V3: read/analyze/generate/write)
    step_type = getattr(current_step, "step_type", "read")
    tool_calls_made = len(current_step_tool_results)

    # Build context sections
    # Previous step results (last FULL_DETAIL_STEPS in full, older summarized)
    prev_step_section = _format_step_results(step_results, current_step_index)
    this_step_section = _format_current_step_results(current_step_tool_results, tool_calls_made)
    
    # Conversation context (full for Act - last 2 turns, entities, etc.)
    conversation_section = format_full_context(
        conversation, step_results, current_step_index, ACT_CONTEXT_THRESHOLD
    )
    
    # Content archive (generated content from previous turns)
    content_archive = state.get("content_archive", {})
    archive_section = ""
    if content_archive:
        archive_lines = ["### Available Archives (from previous turns)"]
        archive_lines.append("Use `{\"action\": \"retrieve_archive\", \"archive_key\": \"...\"}` to fetch full content.")
        for key, val in content_archive.items():
            desc = val.get("description", "No description")[:80]
            archive_lines.append(f"- `{key}`: {desc}")
        archive_section = "\n".join(archive_lines) + "\n"

    # Turn entities (IDs created earlier in this turn - for cross-step linking)
    turn_entities = state.get("turn_entities", [])
    turn_entities_section = _format_turn_entities(turn_entities)
    if turn_entities_section:
        turn_entities_section = turn_entities_section + "\n\n"

    # Common context block (reused across all step types)
    # NOTE: We intentionally DON'T show "Original Goal" here.
    # The step description is the ONLY scope for this turn.
    # Showing the full goal causes Act to optimize for the whole goal instead of the step.
    context_block = f"""---

## Context

### Conversation History
{conversation_section}

{archive_section}
{prev_step_section}

{this_step_section}

---"""

    # Fetch user profile for analyze/generate steps (async enrichment)
    profile_section = ""
    if step_type in ("analyze", "generate"):
        try:
            user_id = state.get("user_id")
            if user_id:
                profile = await get_cached_profile(user_id)
                profile_section = format_profile_for_prompt(profile)
        except Exception:
            pass  # Profile is optional, don't fail on errors

    # Build prompt based on step type
    # Unified prompt structure for all step types:
    # 1. Task (orientation: step #, description, type)
    # 2. This Step (current state: loop status, tool results)
    # 3. Resources (toolkit: schema for CRUD, data for analyze/generate)
    # 4. Context (background: previous steps, conversation)
    # 5. Instructions (what to do next)
    
    today = date.today().isoformat()
    
    if step_type == "analyze":
        # Get subdomain content and analysis guidance
        subdomain_content = get_full_subdomain_content(current_step.subdomain, "analyze")
        
        prev_subdomain = None
        if current_step_index > 0 and think_output and len(think_output.steps) > current_step_index - 1:
            prev_subdomain = think_output.steps[current_step_index - 1].subdomain
        
        analyze_guidance = get_contextual_examples(
            subdomain=current_step.subdomain,
            step_description=current_step.description,
            prev_subdomain=prev_subdomain,
            step_type="analyze",
        )
        
        subdomain_header = ""
        if subdomain_content:
            subdomain_header = f"""{subdomain_content}

---

"""
        
        user_prompt = f"""{subdomain_header}## STATUS
| Step | {current_step_index + 1} of {len(steps)} |
| Goal | {current_step.description} |
| Type | analyze (no db calls) |
| Today | {today} |

---

{profile_section}

## 1. Task

User said: "{state.get("user_message", "")}"

Your job this step: **{current_step.description}**

---

{analyze_guidance}

---

## 2. Data Available

{turn_entities_section}{prev_step_section if prev_step_section else "*No previous step data.*"}

{archive_section}---

## 3. Context

{conversation_section if conversation_section else "*No additional context.*"}

---

## DECISION

Analyze the data above and complete the step:
`{{"action": "step_complete", "result_summary": "Analysis: ...", "data": {{"key": "value"}}}}`"""

    elif step_type == "generate":
        # Get subdomain content (intro + generate persona)
        subdomain_content = get_full_subdomain_content(current_step.subdomain, "generate")
        subdomain_header = ""
        if subdomain_content:
            subdomain_header = f"""{subdomain_content}

---

"""
        
        # Get generation guidance based on subdomain
        generate_guidance = get_contextual_examples(
            subdomain=current_step.subdomain,
            step_description=current_step.description,
            prev_subdomain=None,  # Less relevant for generate
            step_type="generate",
        )
        
        user_prompt = f"""{subdomain_header}## STATUS
| Step | {current_step_index + 1} of {len(steps)} |
| Goal | {current_step.description} |
| Type | generate (create content, no db calls) |
| Today | {today} |

---

{profile_section}

## 1. Task

User said: "{state.get("user_message", "")}"

Your job this step: **{current_step.description}**

---

{generate_guidance}

---

## 2. Data Available

{turn_entities_section}{prev_step_section if prev_step_section else "*No previous step data.*"}

{archive_section}---

## 3. Context

{conversation_section if conversation_section else "*No additional context.*"}

---

## DECISION

Generate the requested content and complete the step:
`{{"action": "step_complete", "result_summary": "Generated: ...", "data": {{"your_content": "here"}}}}`"""

    else:
        # Read/write step - needs schema as primary resource
        subdomain_schema = await get_schema_with_fallback(current_step.subdomain)
        
        # Get combined subdomain content (intro + step-type persona)
        subdomain_content = get_full_subdomain_content(current_step.subdomain, step_type)
        
        # Get previous step's subdomain for cross-domain pattern detection
        prev_subdomain = None
        if current_step_index > 0 and think_output and len(think_output.steps) > current_step_index - 1:
            prev_subdomain = think_output.steps[current_step_index - 1].subdomain
        
        # Get contextual examples based on step verb and cross-domain patterns
        contextual_examples = get_contextual_examples(
            subdomain=current_step.subdomain,
            step_description=current_step.description,
            prev_subdomain=prev_subdomain,
            step_type=step_type,
        )
        
        # Build a quick status summary for the last tool call
        last_tool_summary = ""
        if current_step_tool_results:
            last_item = current_step_tool_results[-1]
            # Handle both (tool, table, result) and (tool, result) formats
            if len(last_item) == 3:
                last_tool, _table, last_result = last_item
            else:
                last_tool, last_result = last_item
            if isinstance(last_result, list):
                last_tool_summary = f" → Last: `{last_tool}` returned {len(last_result)} records"
            elif isinstance(last_result, dict):
                last_tool_summary = f" → Last: `{last_tool}` returned 1 record"
            else:
                last_tool_summary = f" → Last: `{last_tool}` completed"
        
        # Build prev step note section
        prev_note_section = ""
        if prev_step_note:
            prev_note_section = f"""## Previous Step Note

{prev_step_note}

---

"""
        
        # Build subdomain header (intro + step-type persona)
        dynamic_header = ""
        if subdomain_content:
            dynamic_header = f"""{subdomain_content}

---

"""
        
        user_prompt = f"""{dynamic_header}## STATUS
| Step | {current_step_index + 1} of {len(steps)} |
| Goal | {current_step.description} |
| Type | {step_type} |
| Progress | {tool_calls_made} tool calls{last_tool_summary} |
| Today | {today} |

---

{prev_note_section}## 1. Task

User said: "{state.get("user_message", "")}"

Your job this step: **{current_step.description}**

---

## 2. Tool Results This Step

{this_step_section if this_step_section else "*No tool calls yet — make your first db_ call.*"}

---

## 3. Schema ({current_step.subdomain})

{subdomain_schema}

---

{contextual_examples if contextual_examples else ""}

## 4. Previous Steps

{turn_entities_section}{prev_step_section if prev_step_section else "*No previous steps.*"}

{archive_section}---

## 5. Context

{conversation_section if conversation_section else "*No additional context.*"}

---

## DECISION

What's next?
- Step done? → `{{"action": "step_complete", "result_summary": "...", "data": {{...}}, "note_for_next_step": "..."}}`
- Need data? → `{{"action": "tool_call", "tool": "db_read", "params": {{"table": "...", "filters": [...], "limit": N}}}}`
- Need to create? → `{{"action": "tool_call", "tool": "db_create", "params": {{"table": "...", "data": {{...}}}}}}`

**Note for next step:** When completing, include a brief note with IDs or key info the next step might need."""

    # Call LLM for decision (step_results are already in the prompt)
    decision = await call_llm(
        response_model=ActDecision,
        system_prompt=_get_system_prompt(step_type),
        user_prompt=user_prompt,
        complexity=current_step.complexity,
    )

    # Handle request_schema - fetch additional schema and retry
    if decision.action == "request_schema" and decision.subdomain:
        if schema_requests >= 2:
            # Too many schema requests - blocked
            return {
                "pending_action": BlockedAction(
                    reason_code="PLAN_INVALID",
                    details="Too many schema requests. Plan may need revision.",
                    suggested_next="replan",
                ),
            }

        # This would add the schema to context and loop back
        # For now, just increment counter and let it try again
        return {
            "schema_requests": schema_requests + 1,
            "current_subdomain": decision.subdomain,
        }

    # Handle retrieve_step - fetch older step data and include in next prompt
    if decision.action == "retrieve_step" and decision.step_index is not None:
        requested_idx = decision.step_index
        
        # Validate step index
        if requested_idx < 0 or requested_idx >= current_step_index:
            return {
                "pending_action": BlockedAction(
                    reason_code="PLAN_INVALID",
                    details=f"Invalid step index {requested_idx}. Only steps 0-{current_step_index - 1} are available.",
                    suggested_next="ask_user",
                ),
            }
        
        # Retrieve the step data
        retrieved_data = step_results.get(requested_idx)
        
        if retrieved_data is None:
            return {
                "pending_action": BlockedAction(
                    reason_code="PLAN_INVALID",
                    details=f"Step {requested_idx} has no stored data.",
                    suggested_next="ask_user",
                ),
            }
        
        # Add retrieved data to current step's tool results so it appears in context
        # This acts like a "virtual tool call" that returns the old step data
        new_tool_results = current_step_tool_results + [
            (f"retrieve_step_{requested_idx}", retrieved_data)
        ]
        
        return {
            "pending_action": RetrieveStepAction(step_index=requested_idx),
            "current_step_tool_results": new_tool_results,
        }

    # Handle tool_call - execute but DON'T advance step
    # LLM must explicitly call step_complete to advance
    if decision.action == "tool_call" and decision.tool and decision.params:
        # Fix common LLM hallucinations and validate params
        fixed_params, validation_error = _fix_and_validate_tool_params(decision.tool, decision.params)
        if validation_error:
            return {
                "pending_action": BlockedAction(
                    reason_code="TOOL_FAILURE",
                    details=f"Invalid tool params (unfixable): {validation_error}",
                    suggested_next="replan",
                ),
            }
        
        try:
            # Execute the CRUD tool with fixed params
            result = await execute_crud(
                tool=decision.tool,
                params=fixed_params,  # Use fixed params
                user_id=user_id,
            )

            # Append to current step's tool results (accumulate within step)
            # Store as (tool_name, table, result) tuple for entity card support
            table_name = fixed_params.get("table", "unknown")
            new_tool_results = current_step_tool_results + [(decision.tool, table_name, result)]

            # Return ToolCallAction - will loop back for more operations
            action = ToolCallAction(
                tool=decision.tool,
                params=decision.params,
            )

            return {
                "pending_action": action,
                "current_step_tool_results": new_tool_results,
                # Note: NO step_index increment - step continues
            }

        except Exception as e:
            # Tool call failed
            return {
                "pending_action": BlockedAction(
                    reason_code="TOOL_FAILURE",
                    details=f"CRUD operation failed: {str(e)}",
                    suggested_next="ask_user",
                ),
            }

    # Handle retrieve_archive - fetch generated content from previous turns
    if decision.action == "retrieve_archive" and decision.archive_key:
        content_archive = state.get("content_archive", {})
        if decision.archive_key in content_archive:
            archived = content_archive[decision.archive_key]
            # Add archived data to current step's tool results so it's visible
            new_tool_results = current_step_tool_results + [
                (f"archive:{decision.archive_key}", archived.get("data"))
            ]
            return {
                "pending_action": RetrieveStepAction(step_index=-1),  # Special marker
                "current_step_tool_results": new_tool_results,
            }
        else:
            # Archive key not found
            available_keys = list(content_archive.keys())
            return {
                "pending_action": BlockedAction(
                    reason_code="INSUFFICIENT_INFO",
                    details=f"Archive key '{decision.archive_key}' not found. Available: {available_keys}",
                    suggested_next="ask_user",
                ),
            }

    # Handle step_complete - NOW we advance the step
    if decision.action == "step_complete":
        # For read/write steps: keep the actual tool results (not LLM's summary)
        # For analyze/generate: use decision.data (LLM's output IS the result)
        if step_type in ("read", "write") and current_step_tool_results:
            # Preserve actual DB results - critical for later analyze steps
            step_data = current_step_tool_results
        elif decision.data is not None:
            step_data = decision.data
        else:
            step_data = current_step_tool_results
        
        # Cache the combined result for this step
        new_step_results = step_results.copy()
        new_step_results[current_step_index] = step_data

        # Extract note for next step (read/write steps only)
        note_for_next = None
        if step_type in ("read", "write") and hasattr(decision, 'note_for_next_step'):
            note_for_next = decision.note_for_next_step

        action = StepCompleteAction(
            result_summary=decision.result_summary or "Step completed",
            data=step_data,
            note_for_next_step=note_for_next,
        )
        
        # Archive generate/analyze step results for cross-turn retrieval
        # This allows "save those recipes" to work even in a later turn
        new_archive = state.get("content_archive", {}).copy()
        if step_type in ("generate", "analyze") and step_data:
            # Create a descriptive archive key
            archive_key = f"step_{current_step_index}_{step_type}"
            # Also try to create a semantic key based on step description
            desc_lower = current_step.description.lower()
            if "recipe" in desc_lower:
                archive_key = "generated_recipes"
            elif "meal" in desc_lower and "plan" in desc_lower:
                archive_key = "generated_meal_plan"
            elif "analyz" in desc_lower or "compar" in desc_lower:
                archive_key = "analysis_result"
            
            new_archive[archive_key] = {
                "step_index": current_step_index,
                "step_type": step_type,
                "description": current_step.description,
                "data": step_data,
            }

        # V3: Extract and tag entities for lifecycle tracking
        current_turn = state.get("current_turn", 0)
        new_entities = _extract_turn_entities(
            step_data, 
            current_step_index, 
            step_type,
            current_turn,
        )
        
        # Touch existing entities that appear in step results
        # This keeps them "alive" for garbage collection purposes
        from alfred.core.entities import EntityRegistry
        registry_data = state.get("entity_registry", {})
        registry = EntityRegistry.from_dict(registry_data) if registry_data else EntityRegistry()
        
        for entity in new_entities:
            # If entity already exists in registry, touch it
            if registry.get(entity.id):
                registry.touch(entity.id, current_turn)
        
        # Convert to dicts for state storage
        existing_entities = state.get("turn_entities", [])
        new_entity_dicts = [e.to_dict() for e in new_entities]
        accumulated_entities = existing_entities + new_entity_dicts

        return {
            "pending_action": action,
            "current_step_index": current_step_index + 1,
            "step_results": new_step_results,
            "current_step_tool_results": [],  # Reset for next step
            "schema_requests": 0,
            "content_archive": new_archive,
            "prev_step_note": note_for_next,  # Pass note to next step
            "turn_entities": accumulated_entities,  # Accumulated entity IDs
            "entity_registry": registry.to_dict(),  # Update registry with touched entities
        }

    # Handle other actions (ask_user, blocked, fail)
    action = _decision_to_action(decision)
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
    if isinstance(pending_action, ToolCallAction):
        # Tool executed but step not complete - loop back for more
        # This enables multi-tool-call pattern within a single step
        return "continue"

    if isinstance(pending_action, StepCompleteAction):
        # Step explicitly completed - check if more steps remain
        if think_output and current_step_index < len(think_output.steps):
            return "continue"
        return "reply"

    if isinstance(pending_action, RequestSchemaAction):
        # Loop back to try with new schema
        return "continue"

    if isinstance(pending_action, RetrieveStepAction):
        # Retrieved older step data - loop back with data in context
        return "continue"

    if isinstance(pending_action, AskUserAction):
        return "ask_user"

    if isinstance(pending_action, BlockedAction):
        # For now, treat blocked as needing reply
        return "reply"

    if isinstance(pending_action, FailAction):
        return "fail"

    return "reply"


# =============================================================================
# Act Quick Node (Phase 3)
# =============================================================================


class ActQuickParams(BaseModel):
    """Params for quick mode CRUD operations."""
    table: str = Field(description="Table name (inventory, shopping_list, etc.)")
    filters: list[dict[str, Any]] = Field(default_factory=list, description="Filter clauses for read/update/delete")
    data: dict[str, Any] | list[dict[str, Any]] | None = Field(default=None, description="Record data for create/update")
    limit: int | None = Field(default=None, description="Max rows to return for read")


class ActQuickDecision(BaseModel):
    """
    Simplified decision model for Quick Mode.
    
    Only tool_call is supported - no step_complete loop.
    """
    
    tool: Literal["db_read", "db_create", "db_update", "db_delete"] = Field(
        description="CRUD tool to call"
    )
    params: ActQuickParams = Field(
        description="Tool parameters with table, filters, data, limit"
    )


async def act_quick_node(state: AlfredState) -> dict[str, Any]:
    """
    Quick mode Act node - single-call execution without step_complete loop.
    
    Phase 3: Skips Think, receives intent directly from Understand.
    Executes ONE tool call and goes directly to Reply.
    
    Args:
        state: Current graph state with understand_output containing quick_intent/quick_subdomain
        
    Returns:
        State update with step_results for Reply to format
    """
    set_current_node("act_quick")
    
    # Get quick mode data from understand output
    understand_output = state.get("understand_output")
    if not understand_output:
        logger.error("Act Quick: No understand output")
        return {"error": "No understand output for quick mode"}
    
    quick_intent = getattr(understand_output, "quick_intent", None)
    quick_subdomain = getattr(understand_output, "quick_subdomain", None)
    
    if not quick_intent or not quick_subdomain:
        logger.error("Act Quick: Missing quick_intent or quick_subdomain")
        return {"error": "Missing quick mode fields"}
    
    logger.info(f"Act Quick: intent='{quick_intent}', subdomain='{quick_subdomain}'")
    
    # Get schema for the subdomain
    subdomain_schema = await get_schema_with_fallback(quick_subdomain)
    
    # Build prompt using shared components
    user_id = state.get("user_id", "")
    today = date.today().isoformat()
    
    # Infer action type from intent for better example selection
    intent_lower = quick_intent.lower()
    if any(verb in intent_lower for verb in ["add", "create", "insert", "save"]):
        action_type = "create"
    elif any(verb in intent_lower for verb in ["update", "change", "modify", "set"]):
        action_type = "update"
    elif any(verb in intent_lower for verb in ["delete", "remove", "clear"]):
        action_type = "delete"
    else:
        action_type = "read"
    
    # Get user's original message - CRITICAL for data extraction
    user_message = state.get("user_message", "")
    
    # Get conversation context for session awareness
    conversation = state.get("conversation", {})
    engagement_summary = conversation.get("engagement_summary", "")
    
    # Get user preferences for safety (allergies, restrictions)
    user_preferences = None
    if user_id:
        try:
            profile = await get_cached_profile(user_id)
            user_preferences = {
                "allergies": profile.allergies,
                "dietary_restrictions": profile.dietary_restrictions,
            }
        except Exception:
            pass  # Preferences are optional
    
    # Build prompt using shared injection module
    system_prompt, user_prompt = build_act_quick_prompt(
        intent=quick_intent,
        subdomain=quick_subdomain,
        action_type=action_type,
        schema=subdomain_schema,
        today=today,
        user_message=user_message,
        engagement_summary=engagement_summary,
        user_preferences=user_preferences,
    )

    try:
        # Single LLM call
        decision = await call_llm(
            response_model=ActQuickDecision,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            complexity="low",  # Quick mode uses fast model
        )
        
        logger.info(f"Act Quick: tool={decision.tool}, expected_action={action_type}")
        
        # Log warning if tool doesn't match expected action (but trust LLM's choice)
        expected_tool_map = {
            "read": "db_read",
            "create": "db_create",
            "update": "db_update",
            "delete": "db_delete",
        }
        expected_tool = expected_tool_map.get(action_type, "db_read")
        
        if decision.tool != expected_tool:
            logger.warning(
                f"Act Quick: Tool mismatch! Intent analysis said '{action_type}' but LLM chose '{decision.tool}'. "
                f"Trusting LLM's choice but this may indicate a prompt issue."
            )
        
        # Convert structured params to dict for CRUD
        params = decision.params.model_dump(exclude_none=True)
        
        # Ensure table is set
        if not params.get("table"):
            table_map = {
                "inventory": "inventory",
                "shopping": "shopping_list",
                "recipes": "recipes",
                "meal_plans": "meal_plans",
                "tasks": "tasks",
                "preferences": "preferences",
            }
            params["table"] = table_map.get(quick_subdomain, quick_subdomain)
        
        # Ensure filters exists for read operations
        if "filters" not in params:
            params["filters"] = []
        if decision.tool == "db_read" and "limit" not in params:
            params["limit"] = 100
        
        # Validate and fix params
        fixed_params, error = _fix_and_validate_tool_params(decision.tool, params)
        if error:
            logger.error(f"Act Quick: Param validation failed (unfixable): {error}")
            return {
                "error": f"Invalid tool parameters: {error}",
                "step_results": {},
            }
        
        # Execute the tool
        result = await execute_crud(
            tool=decision.tool,
            params=fixed_params,
            user_id=user_id,
        )
        
        logger.info(f"Act Quick: Got {len(result) if isinstance(result, list) else 1} results")
        
        # Store result for Reply
        step_results = {
            0: [(decision.tool, quick_subdomain, result)]  # Format like normal act results
        }
        
        # Extract entities for tracking
        current_turn = state.get("current_turn", 0)
        step_type = "read" if decision.tool == "db_read" else "write"
        new_entities = _extract_turn_entities(
            step_results[0],
            0,
            step_type,
            current_turn,
        )
        
        # Convert to dicts for state storage
        new_entity_dicts = [e.to_dict() for e in new_entities]
        
        return {
            "step_results": step_results,
            "current_step_index": 1,  # Mark as complete
            "turn_entities": new_entity_dicts,
            "quick_result": result,  # Direct result for Reply Quick
        }
        
    except Exception as e:
        logger.exception(f"Act Quick failed: {e}")
        return {
            "error": f"Act Quick failed: {str(e)}",
            "step_results": {},
        }


def should_continue_act_quick(state: AlfredState) -> str:
    """
    Quick mode always goes directly to Reply after execution.
    
    No looping - single call, done.
    """
    return "reply"
