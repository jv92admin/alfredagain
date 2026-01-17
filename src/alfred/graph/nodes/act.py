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
import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from alfred.core.modes import Mode, ModeContext
from alfred.core.id_registry import SessionIdRegistry
from alfred.core.payload_compiler import compile_payloads, get_compiled_payload_for_step
from alfred.graph.state import (
    ACT_CONTEXT_THRESHOLD,
    FULL_DETAIL_STEPS,
    ActAction,
    AlfredState,
    AskUserAction,
    BatchItem,
    BatchManifest,
    BatchProgress,
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
from alfred.prompts.injection import build_act_prompt, build_act_user_prompt
from alfred.tools.crud import execute_crud
from alfred.tools.schema import get_schema_with_fallback
from alfred.prompts.personas import get_full_subdomain_content
from alfred.prompts.examples import get_contextual_examples

# Entity types to track across steps
TRACKED_ENTITY_TYPES = {"recipes", "meal_plans", "tasks", "recipe", "meal_plan", "task"}


def _infer_entity_type_from_artifact(artifact: dict) -> str:
    """Infer entity type from artifact structure. V4 CONSOLIDATION."""
    if "instructions" in artifact or "cuisine" in artifact or "prep_time" in artifact:
        return "recipe"
    # Flat meal plan entry
    if "meal_type" in artifact and "date" in artifact:
        return "meal_plan"
    # Nested meal plan structure: {"meal_plan": [...]} or has "meals" key
    if "meal_plan" in artifact or "meals" in artifact:
        return "meal_plan"
    if "due_date" in artifact or ("title" in artifact and "status" in artifact):
        return "task"
    if artifact.get("type"):
        return artifact["type"]
    return "item"


def _extract_artifact_label(artifact: dict, entity_type: str, index: int) -> str:
    """Extract a human-readable label from an artifact."""
    # Standard name/title fields
    if artifact.get("name"):
        return artifact["name"]
    if artifact.get("title"):
        return artifact["title"]
    
    # Meal plan: try to extract date range
    if entity_type == "meal_plan":
        meal_plan = artifact.get("meal_plan", [])
        if meal_plan and isinstance(meal_plan, list):
            dates = [entry.get("date") for entry in meal_plan if entry.get("date")]
            if dates:
                return f"Meal Plan {dates[0]} to {dates[-1]}"
        return f"Generated Meal Plan"
    
    return f"item_{index + 1}"


# V4 CONSOLIDATION: _extract_turn_entities and _format_turn_entities removed
# Entity tracking is now handled exclusively by SessionIdRegistry


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
    
    Layers (Act is execution, not user-facing — no system.md):
    1. base.md - Act's role in Alfred (execution engine)
    2. crud.md - Tools, filters, operators (only for read/write)
    3. {step_type}.md - Mechanics for this step type
    
    Subdomain content (persona, user profile, schema) is added to user_prompt.
    """
    base = _load_prompt("base.md")
    step_type_content = _load_prompt(f"{step_type}.md")
    
    # Build layers: base → (crud) → step_type
    parts = [base]
    
    # CRUD steps need the tools reference
    if step_type in ("read", "write"):
        crud = _load_prompt("crud.md")
        if crud:
            parts.append(crud)
    
    # Add step-type-specific content (read.md, write.md, analyze.md, generate.md)
    if step_type_content:
        parts.append(step_type_content)
    
    return "\n\n---\n\n".join(parts)


def _format_step_results(
    step_results: dict[int, Any], 
    current_index: int,
    step_metadata: dict[int, dict] | None = None,
    current_step_type: str | None = None,
) -> str:
    """Format previous step results for context.
    
    V4 Changes:
    - For write steps following generate steps, inject FULL artifact content
    - step_metadata tracks step_type and artifacts per step
    - No more "(use retrieve_step for details)" for generate step content
    
    Last FULL_DETAIL_STEPS get FULL data (essential for analyze steps).
    Older steps get summarized (except generate artifacts for write steps).
    
    Uses table-aware formatting to reduce token bloat while preserving
    the critical info (IDs, names) that Act needs for subsequent steps.
    """
    import json
    from alfred.prompts.injection import _format_records_for_table, _infer_table_from_record
    
    if not step_results:
        return "### Previous Step Results\n*No previous steps completed yet.*"

    lines = ["### Previous Step Results", ""]
    step_metadata = step_metadata or {}
    
    # Determine which steps get full detail
    max_step = max(step_results.keys()) if step_results else -1
    full_detail_threshold = max_step - FULL_DETAIL_STEPS + 1  # Last N steps get full detail
    
    # V4: Check if current step is a write step - if so, we need full artifacts from generate steps
    is_write_step = current_step_type == "write"

    for idx in sorted(step_results.keys()):
        result = step_results[idx]
        step_num = idx + 1
        is_recent = idx >= full_detail_threshold
        
        # V4: Get step metadata for this step
        metadata = step_metadata.get(idx, {})
        was_generate_step = metadata.get("step_type") == "generate"
        artifacts = metadata.get("artifacts")
        
        # V4: For write steps following generate, always show full artifacts
        # This is the key fix - generated content must be available for saving
        if is_write_step and was_generate_step and artifacts:
            step_desc = metadata.get("description", "Generated content")
            subdomain = metadata.get("subdomain", "recipes")
            lines.append(f"**Step {step_num}** [generate] — {step_desc}:")
            lines.append("")
            lines.append("## Data from Step {} (for db_create)".format(step_num))
            lines.append("")
            
            # V4: Use payload compiler to pre-normalize content for write
            compiled = compile_payloads(subdomain, artifacts, {})
            if compiled.success and compiled.payloads:
                lines.append("### Pre-Compiled Payloads (schema-ready)")
                lines.append("")
                for payload in compiled.payloads:
                    for record in payload.records:
                        lines.append(f"**{record.ref}** → `{payload.target_table}`:")
                        lines.append("```json")
                        lines.append(json.dumps(record.data, indent=2, default=str))
                        lines.append("```")
                        # Show linked records if any
                        if record.linked_records:
                            for linked in record.linked_records:
                                lines.append(f"  └─ `{linked.table}`: {len(linked.records)} records")
                        lines.append("")
                
                # Surface compilation warnings
                if compiled.warnings:
                    lines.append("⚠️ **Compilation Notes:**")
                    for warning in compiled.warnings:
                        lines.append(f"  - {warning}")
                    lines.append("")
            else:
                # Fallback: show raw artifacts if compilation failed
                for i, artifact in enumerate(artifacts):
                    if isinstance(artifact, dict):
                        ref = artifact.get("temp_id") or artifact.get("name") or f"item_{i+1}"
                        lines.append(f"### {ref}")
                        lines.append("```json")
                        lines.append(json.dumps(artifact, indent=2, default=str))
                        lines.append("```")
                        lines.append("")
            continue
        
        # Parse result format: [(tool_name, subdomain, result_data), ...]
        if isinstance(result, list) and result and isinstance(result[0], tuple):
            for tool_call in result:
                if len(tool_call) >= 3:
                    tool_name, subdomain, data = tool_call[:3]
                    # Map subdomain to table (they usually match)
                    table = _subdomain_to_table(subdomain)
                    lines.append(f"**Step {step_num}** [{tool_name}] on `{table}`:")
                    if is_recent:
                        lines.extend(_format_step_data_clean(data, table))
                    else:
                        lines.append(_summarize_step_data(data, table))
        elif isinstance(result, list):
            table = _infer_table_from_record(result[0]) if result else None
            lines.append(f"**Step {step_num}** ({len(result)} records):")
            if is_recent:
                lines.extend(_format_step_data_clean(result, table))
            else:
                lines.append(f"  {len(result)} records")
        elif isinstance(result, int):
            lines.append(f"**Step {step_num}**: Affected {result} records")
        elif was_generate_step and artifacts:
            # Generate step with artifacts - show summary with artifact count
            lines.append(f"**Step {step_num}** [generate]: {len(artifacts)} items generated")
            if is_recent:
                # Show brief labels
                for artifact in artifacts[:5]:
                    if isinstance(artifact, dict):
                        label = artifact.get("name") or artifact.get("temp_id") or "item"
                        lines.append(f"  - {label}")
                if len(artifacts) > 5:
                    lines.append(f"  ... and {len(artifacts) - 5} more")
        elif was_generate_step and result:
            # V4: For generate steps without explicit artifacts, try to format the data
            lines.append(f"**Step {step_num}** [generate]: Content generated")
            if is_recent and isinstance(result, dict):
                lines.append("```json")
                lines.append(json.dumps(result, indent=2, default=str)[:2000])
                lines.append("```")
        elif metadata.get("step_type") == "analyze":
            # Analyze steps produce conclusions - ALWAYS show these IN FULL (crucial for next step)
            # These contain clarifications, constraints, and recommendations that Generate needs
            step_desc = metadata.get("description", "Analysis")
            lines.append(f"**Step {step_num}** [analyze] — {step_desc}:")
            if isinstance(result, dict):
                # Show the analysis result directly - NO TRUNCATION for analyze outputs
                lines.append("```json")
                lines.append(json.dumps(result, indent=2, default=str))
                lines.append("```")
            elif isinstance(result, str):
                lines.append(f"  {result}")
            else:
                lines.append("  Analysis completed")
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


def _subdomain_to_entity_type(subdomain: str) -> str:
    """Map subdomain to entity type for SessionIdRegistry refs."""
    mapping = {
        "inventory": "inv",
        "shopping": "shopping",
        "recipes": "recipe",
        "meal_plans": "meal_plan",
        "tasks": "task",
        "preferences": "preference",
    }
    return mapping.get(subdomain, subdomain)


def _normalize_subdomain(raw: str) -> str:
    """
    Normalize approximate subdomain to canonical value.
    
    Single source of truth for valid subdomains.
    Understand passes natural/approximate values, Act Quick normalizes.
    """
    raw_lower = raw.lower().strip()
    
    # Canonical values (no change needed)
    canonical = {"inventory", "recipes", "shopping", "meal_plans", "preferences"}
    if raw_lower in canonical:
        return raw_lower
    
    # Common variations → canonical
    aliases = {
        # Singular → plural
        "recipe": "recipes",
        "meal_plan": "meal_plans",
        "preference": "preferences",
        # Natural language
        "pantry": "inventory",
        "fridge": "inventory",
        "ingredients": "inventory",
        "shopping_list": "shopping",
        "groceries": "shopping",
        "meals": "meal_plans",
        "meal planning": "meal_plans",
        "diet": "preferences",
        "dietary": "preferences",
        "restrictions": "preferences",
    }
    
    if raw_lower in aliases:
        logger.info(f"Normalized subdomain: {raw} → {aliases[raw_lower]}")
        return aliases[raw_lower]
    
    # Unknown - return as-is (will fail at schema lookup with clear error)
    logger.warning(f"Unknown subdomain: {raw}")
    return raw_lower


def _format_step_data_clean(data: Any, table: str | None) -> list[str]:
    """Format step data in clean, readable format with IDs preserved.
    
    V4: IDs are now simple refs (recipe_1, inv_5) from the registry,
    so we display them in full (no truncation needed).
    """
    from alfred.prompts.injection import _format_records_for_table
    
    if isinstance(data, list):
        if not data:
            return ["  (no records)"]
        formatted = _format_records_for_table(data, table)
        # V4: IDs are simple refs - display in full
        ids = [str(r.get("id")) for r in data if isinstance(r, dict) and r.get("id")]
        if ids:
            formatted.append(f"  **IDs:** {', '.join(ids)}")
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


def _build_enhanced_entity_context(
    session_registry: SessionIdRegistry,
    current_step_index: int,
    current_step_results: dict[int, Any],
    turn_step_results: dict[str, dict],
) -> str:
    """
    V5: Build enhanced entity context with FULL DATA for active entities.
    
    This is the key to Act seeing entity data without re-reading:
    - Active entities (last 2 turns + current): Show full data
    - Long-term memory (>2 turns): Show refs only
    
    Token cost: ~20-40 lines per entity vs 300+ lines for 2 LLM calls (read + step_complete)
    
    See docs/prompts/act-prompt-structure.md for the full specification.
    
    Args:
        session_registry: SessionIdRegistry with entity refs
        current_step_index: Current step being executed
        current_step_results: This turn's step_results
        turn_step_results: Prior turns' step_results from conversation
        
    Returns:
        Formatted entity context string
    """
    from alfred.prompts.injection import _format_records_for_table, _infer_table_from_record
    import json
    
    lines = []
    
    # Get active entities split by source
    recent_refs, retained_refs = session_registry.get_active_entities(turns_window=2)
    
    # Section 1: Artifacts needing main record created (same as before)
    truly_pending = session_registry.get_truly_pending_artifacts()
    if truly_pending:
        lines.append("## Needs Creating")
        lines.append("These items need their main record saved:")
        lines.append("")
        for ref, artifact in truly_pending.items():
            label = artifact.get("name") or artifact.get("label") or ref
            entity_type = session_registry.ref_types.get(ref, "unknown")
            lines.append(f"- `{ref}`: {label} ({entity_type})")
        lines.append("")
    
    # Section 1b: Just promoted this turn (same as before)
    just_promoted = session_registry.get_just_promoted_artifacts()
    if just_promoted:
        lines.append("## Just Saved This Turn")
        lines.append("Main record created. For linked tables (recipe_ingredients), use the ref as FK:")
        lines.append("")
        for ref, artifact in just_promoted.items():
            label = artifact.get("name") or artifact.get("label") or ref
            entity_type = session_registry.ref_types.get(ref, "unknown")
            uuid = session_registry.ref_to_uuid.get(ref, "?")[:8]
            lines.append(f"- `{ref}`: {label} ({entity_type}) → saved as {uuid}...")
        lines.append("")
    
    # Section 2: Active Entity Data (FULL DATA from step_results)
    # Collect entity data from current turn + prior 2 turns
    entity_data_by_ref = {}  # {ref: {table, data}} - latest wins for dedup
    
    # First, collect from prior turns (oldest first so newer overwrites)
    for turn_num in sorted(turn_step_results.keys(), key=int):
        turn_data = turn_step_results[turn_num]
        for step_key, step_data in turn_data.items():
            data = step_data.get("data")
            table = step_data.get("table")
            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict) and record.get("id"):
                        ref = str(record["id"])
                        entity_data_by_ref[ref] = {"table": table, "data": record, "turn": turn_num}
    
    # Then from current turn (overwrites prior)
    current_turn = str(session_registry.current_turn)
    for step_idx, result in current_step_results.items():
        # Handle tool result tuples
        if isinstance(result, list) and result and isinstance(result[0], tuple):
            for item in result:
                if len(item) >= 3:
                    tool, table, data = item[:3]
                elif len(item) == 2:
                    tool, data = item
                    table = None
                else:
                    continue
                    
                if isinstance(data, list):
                    if not table and data:
                        table = _infer_table_from_record(data[0])
                    for record in data:
                        if isinstance(record, dict) and record.get("id"):
                            ref = str(record["id"])
                            entity_data_by_ref[ref] = {"table": table, "data": record, "turn": current_turn}
        elif isinstance(result, list):
            for record in result:
                if isinstance(record, dict) and record.get("id"):
                    ref = str(record["id"])
                    entity_data_by_ref[ref] = {"table": None, "data": record, "turn": current_turn}
    
    # Now format the active entity data
    if entity_data_by_ref:
        lines.append("## Active Entities (Context Snapshot)")
        lines.append("Data from recent turns. **For read steps, always call db_read — this is reference, not a substitute.**")
        lines.append("")
        
        for ref, info in entity_data_by_ref.items():
            table = info.get("table")
            data = info.get("data")
            turn = info.get("turn")
            
            # Skip if not in recent refs (might be deleted or not tracked)
            # But still show if it's in current turn's results
            if ref not in recent_refs and turn != current_turn:
                continue
            
            label = session_registry.ref_labels.get(ref, data.get("name") or data.get("title") or ref)
            entity_type = session_registry.ref_types.get(ref, table or "unknown")
            
            # Format based on entity type
            if table == "recipes" or entity_type == "recipe":
                lines.extend(_format_recipe_data(ref, label, data, session_registry))
            else:
                # Generic format
                lines.append(f"### `{ref}`: {label} ({entity_type})")
                # Show key fields inline
                key_fields = ["quantity", "unit", "location", "category", "date", "meal_type", "status"]
                field_parts = []
                for field in key_fields:
                    if field in data and data[field] is not None:
                        field_parts.append(f"{field}: {data[field]}")
                if field_parts:
                    lines.append(f"  {' | '.join(field_parts)}")
            lines.append("")
    
    # Section 3: Recent Context (refs only for entities NOT in entity_data)
    recent_not_shown = [r for r in recent_refs 
                       if r not in entity_data_by_ref 
                       and r not in truly_pending
                       and r not in just_promoted]
    if recent_not_shown:
        lines.append("## Recent Context (refs only)")
        lines.append("**Refs from last 2 turns — data not loaded. Use db_read if full data needed.**")
        lines.append("")
        for ref in recent_not_shown:
            label = session_registry.ref_labels.get(ref, ref)
            entity_type = session_registry.ref_types.get(ref, "unknown")
            action = session_registry.ref_actions.get(ref, "-")
            lines.append(f"- `{ref}`: {label} ({entity_type}) [{action}]")
        lines.append("")
    
    # Section 4: Long Term Memory (refs only - same as before)
    if retained_refs:
        lines.append("## Long Term Memory (refs only)")
        lines.append("**Older entities retained by Understand — need db_read for data.**")
        lines.append("")
        for ref in retained_refs:
            label = session_registry.ref_labels.get(ref, ref)
            entity_type = session_registry.ref_types.get(ref, "unknown")
            lines.append(f"- `{ref}`: {label} ({entity_type})")
        lines.append("")
    
    if not lines:
        lines.append("## Available Entities")
        lines.append("")
        lines.append("*No entities in context.*")
    
    return "\n".join(lines)


def _format_recipe_data(ref: str, label: str, data: dict, registry: "SessionIdRegistry | None" = None) -> list[str]:
    """Format recipe data for Act context - includes key fields and instruction count.
    
    Checks what data is available and labels appropriately:
    - Full: has instructions AND full ingredients (with id, quantity)
    - Snapshot: missing instructions OR only ingredient names
    
    When registry is provided, ingredient refs are looked up and displayed inline.
    """
    # Check what data we have
    has_instructions = bool(data.get("instructions"))
    ingredients = data.get("recipe_ingredients", [])
    
    # Check if ingredients have full data (not just name/category from auto-include)
    has_full_ingredients = False
    if ingredients and isinstance(ingredients[0], dict):
        # Full ingredients have id, quantity, unit - auto-include only has name, category
        has_full_ingredients = "id" in ingredients[0] or "quantity" in ingredients[0]
    
    # Determine what's missing
    missing = []
    if not has_instructions:
        missing.append("instructions")
    if not has_full_ingredients and ingredients:
        missing.append("ingredient details")
    
    if missing:
        snapshot_indicator = f" *(snapshot — missing: {', '.join(missing)})*"
    else:
        snapshot_indicator = ""
    
    lines = [f"### `{ref}`: {label} (recipe){snapshot_indicator}"]
    
    # Core metadata
    meta = []
    if data.get("cuisine"):
        meta.append(f"cuisine: {data['cuisine']}")
    if data.get("total_time"):
        meta.append(f"time: {data['total_time']}")
    if data.get("servings"):
        meta.append(f"servings: {data['servings']}")
    if data.get("difficulty"):
        meta.append(f"difficulty: {data['difficulty']}")
    if meta:
        lines.append(f"  {' | '.join(meta)}")
    
    # Tags
    tags = []
    if data.get("occasions"):
        tags.append(f"occasions: {', '.join(data['occasions'][:3])}")
    if data.get("health_tags"):
        tags.append(f"health: {', '.join(data['health_tags'][:3])}")
    if tags:
        lines.append(f"  {' | '.join(tags)}")
    
    # Ingredients - format based on whether we have full data
    if ingredients:
        if has_full_ingredients:
            # Full ingredients - show with quantities AND refs for updates
            lines.append(f"  **ingredients ({len(ingredients)} items):**")
            for ing in ingredients:
                qty = ing.get("quantity", "")
                unit = ing.get("unit", "")
                name = ing.get("name", "?")
                qty_str = f"{qty} {unit} " if qty else ""
                
                # Look up ingredient ref if registry available and ingredient has ID
                ing_ref = None
                if registry and ing.get("id"):
                    ing_ref = registry.get_ref(str(ing["id"]))
                
                if ing_ref:
                    lines.append(f"    - `{ing_ref}`: {qty_str}{name}")
                else:
                    lines.append(f"    - {qty_str}{name}")
        else:
            # Summary only (auto-include) - just names
            names = [i.get("name", "?") for i in ingredients[:5]]
            more = f"... ({len(ingredients)} total)" if len(ingredients) > 5 else f" ({len(ingredients)} total)"
            lines.append(f"  ingredients (names only): {', '.join(names)}{more}")
    
    # Instructions - show full content when available
    instructions = data.get("instructions")
    if instructions:
        if isinstance(instructions, list):
            lines.append(f"  **instructions ({len(instructions)} steps):**")
            for i, step in enumerate(instructions, 1):
                # Skip prefix if step already starts with a number (e.g., "1. Prep...")
                if re.match(r'^\d+\.?\s', step):
                    lines.append(f"    {step}")
                else:
                    lines.append(f"    {i}. {step}")
        else:
            lines.append(f"  **instructions:** {instructions}")
    else:
        lines.append("  instructions: not loaded")
    
    return lines


def _format_previous_turn_steps(conversation: dict) -> str:
    """
    V6: Format last 2 steps from previous turn for Act context.
    
    Provides continuity across turns without duplicating full data.
    Shows what happened, not the full results.
    """
    turn_summaries = conversation.get("turn_summaries", [])
    if not turn_summaries:
        return ""
    
    # Get the most recent turn summary (last turn)
    last_turn = turn_summaries[-1]
    steps = last_turn.get("steps", [])
    
    if not steps:
        return ""
    
    # Take last 2 steps from previous turn
    recent_steps = steps[-2:]
    turn_num = last_turn.get("turn_num", "?")
    
    lines = [f"### Previous Turn (Turn {turn_num}) - Last {len(recent_steps)} Steps"]
    lines.append("*For reference — data is in entity context if still active*")
    lines.append("")
    
    for step in recent_steps:
        step_num = step.get("step_num", "?")
        step_type = step.get("step_type", "")
        subdomain = step.get("subdomain", "")
        outcome = step.get("outcome", "")
        entities = step.get("entities_involved", [])
        note = step.get("note")
        
        lines.append(f"**Step {step_num + 1} ({step_type}):** {outcome}")
        if entities:
            lines.append(f"  Entities: {', '.join(entities[:10])}")
        if note:
            lines.append(f"  Note: {note}")
    
    lines.append("")
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
    # V4: Pass step_metadata and current step_type for artifact preservation
    step_metadata = state.get("step_metadata", {})
    prev_step_section = _format_step_results(
        step_results, 
        current_step_index,
        step_metadata=step_metadata,
        current_step_type=step_type,
    )
    this_step_section = _format_current_step_results(current_step_tool_results, tool_calls_made)
    
    # Conversation context (full for Act - last 2 turns, entities, etc.)
    conversation_section = format_full_context(
        conversation, step_results, current_step_index, ACT_CONTEXT_THRESHOLD
    )
    
    # V6: Previous turn steps (last 2 steps from prior turn for continuity)
    prev_turn_section = _format_previous_turn_steps(conversation)
    
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

    # V4 CONSOLIDATION: Load SessionIdRegistry - single source of truth
    registry_data = state.get("id_registry")
    if registry_data is None:
        session_registry = SessionIdRegistry(session_id=state.get("conversation_id", ""))
    elif isinstance(registry_data, SessionIdRegistry):
        session_registry = registry_data
    else:
        session_registry = SessionIdRegistry.from_dict(registry_data)
    session_registry.set_turn(state.get("current_turn", 1))
    
    # V4: Inject generated content from SessionIdRegistry for write steps
    # Shows full JSON data for db_create calls (includes promoted artifacts for linked records)
    pending_artifacts_section = ""
    if step_type == "write":
        pending = session_registry.get_all_pending_artifacts()
        if pending:
            import json
            pa_lines = ["### Generated Data"]
            pa_lines.append("Full content for db_create. Use `recipe_id: \"gen_recipe_X\"` for linked records.")
            pa_lines.append("")
            for ref, content in pending.items():
                label = content.get("name") or content.get("title") or ref
                # Show status: whether main record exists
                action = session_registry.ref_actions.get(ref, "generated")
                status = "[main record saved]" if action == "created" else "[needs main record]"
                pa_lines.append(f"#### {ref}: {label} {status}")
                pa_lines.append("```json")
                pa_lines.append(json.dumps(content, indent=2, default=str))
                pa_lines.append("```")
                pa_lines.append("")
            pending_artifacts_section = "\n".join(pa_lines) + "\n"

    # V4 CONSOLIDATION: Use SessionIdRegistry for all entity display
    # Single source of truth - no separate WorkingSet or EntityContextModel
    
    # Mark referenced entities (from Understand) as touched this turn
    understand_output = state.get("understand_output")
    if understand_output:
        referenced = getattr(understand_output, "referenced_entities", []) or []
        for ref in referenced:
            session_registry.touch_ref(ref)  # Updates last_ref timestamp
    
    # V5: Build enhanced entity context with FULL DATA for active entities
    # Active = last 2 turns + current turn (matches token savings vs re-read cost)
    # Long-term = refs only (need re-read if data required)
    turn_step_results = conversation.get("turn_step_results", {})
    working_set_section = _build_enhanced_entity_context(
        session_registry=session_registry,
        current_step_index=current_step_index,
        current_step_results=step_results,
        turn_step_results=turn_step_results,
    )

    # Fetch user profile and subdomain guidance for analyze/generate/write steps
    profile_section = ""
    subdomain_guidance_section = ""
    if step_type in ("analyze", "generate", "write"):
        try:
            user_id = state.get("user_id")
            if user_id:
                profile = await get_cached_profile(user_id)
                # Profile for analyze/generate/write steps (user constraints matter)
                profile_section = format_profile_for_prompt(profile)
                # Subdomain guidance for all three step types
                if profile.subdomain_guidance:
                    guidance = profile.subdomain_guidance.get(current_step.subdomain, "")
                    if guidance:
                        subdomain_guidance_section = f"""## User Preferences ({current_step.subdomain})

{guidance}

---

"""
        except Exception:
            pass  # Profile is optional, don't fail on errors

    # Build prompt using centralized injection module
    # See docs/prompts/act-prompt-structure.md for the full specification
    
    # Get schema for read/write steps
    subdomain_schema = None
    if step_type in ("read", "write"):
        subdomain_schema = await get_schema_with_fallback(current_step.subdomain)
    
    # Get previous step's subdomain for cross-domain pattern detection
    prev_subdomain = None
    if current_step_index > 0 and think_output and len(think_output.steps) > current_step_index - 1:
        prev_subdomain = think_output.steps[current_step_index - 1].subdomain
    
    # Build batch manifest section if present
    batch_manifest_section_text = ""
    batch_manifest_data = state.get("current_batch_manifest")
    if batch_manifest_data:
        batch_manifest = BatchManifest(**batch_manifest_data)
        batch_manifest_section_text = batch_manifest.to_prompt_table()
    
    # Build the user prompt via centralized function
    user_prompt = build_act_user_prompt(
        # Step info
        step_type=step_type,
        step_index=current_step_index,
        total_steps=len(steps),
        step_description=current_step.description,
        subdomain=current_step.subdomain,
        user_message=state.get("user_message", ""),
        # Context data
        entity_context=working_set_section,
        conversation_context=conversation_section,
        prev_turn_context=prev_turn_section,
        prev_step_results=prev_step_section,
        current_step_results=this_step_section,
        # Step-type specific
        schema=subdomain_schema,
        profile_section=profile_section,
        subdomain_guidance=subdomain_guidance_section,
        batch_manifest_section=batch_manifest_section_text,
        artifacts_section=pending_artifacts_section,
        archive_section=archive_section,
        prev_step_note=prev_step_note,
        # Metadata
        tool_calls_made=tool_calls_made,
        prev_subdomain=prev_subdomain,
    )

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
        
        # V4 CONSOLIDATION: Load SESSION ID registry - single source of truth
        # The registry sits between Act and CRUD - LLMs only see simple refs
        registry_data = state.get("id_registry")
        if registry_data is None:
            session_registry = SessionIdRegistry(session_id=state.get("conversation_id", ""))
        elif isinstance(registry_data, SessionIdRegistry):
            session_registry = registry_data
        else:
            session_registry = SessionIdRegistry.from_dict(registry_data)
        session_registry.set_turn(state.get("current_turn", 1))
        
        try:
            # V4: Execute CRUD with registry - handles ALL ID translation:
            # - Filters: recipe_1 → real UUID before query
            # - Payloads: FK refs → real UUIDs before insert/update
            # - Output: real UUIDs → refs (recipe_1, recipe_2) after query
            result = await execute_crud(
                tool=decision.tool,
                params=fixed_params,
                user_id=user_id,
                registry=session_registry,  # V4: Session registry (persists across turns)
            )

            # Append to current step's tool results (accumulate within step)
            # Store as (tool_name, table, result) tuple for entity card support
            # NOTE: result now contains refs (recipe_1), not UUIDs
            table_name = fixed_params.get("table", "unknown")
            new_tool_results = current_step_tool_results + [(decision.tool, table_name, result)]

            # V4 CONSOLIDATION: Clean up registry on delete
            # This prevents ghost refs from persisting after entities are deleted
            if decision.tool == "db_delete":
                # Extract deleted refs from filters
                filters = fixed_params.get("filters", [])
                deleted_refs = []
                for f in filters:
                    if f.get("field") == "id":
                        value = f.get("value")
                        if isinstance(value, str):
                            deleted_refs.append(value)
                        elif isinstance(value, list):
                            deleted_refs.extend(value)
                
                if deleted_refs:
                    # Mark as deleted but KEEP UUID mapping for subsequent steps
                    # (e.g., need to search meal_plans by deleted recipe_id)
                    for ref in deleted_refs:
                        session_registry.ref_actions[ref] = "deleted"
                    logger.info(f"Act: Marked {len(deleted_refs)} entities as deleted: {deleted_refs}")
            
            # V4: Update batch manifest if present (track completed items)
            updated_batch_manifest = None
            batch_manifest_data = state.get("current_batch_manifest")
            if batch_manifest_data and decision.tool == "db_create":
                batch_manifest = BatchManifest(**batch_manifest_data)
                
                # Try to match created records to batch items
                if isinstance(result, list):
                    for record in result:
                        if isinstance(record, dict) and record.get("id"):
                            # Try to find matching batch item by name/label
                            record_name = record.get("name") or record.get("title") or ""
                            for item in batch_manifest.items:
                                if item.status == "pending":
                                    # Match by label similarity or just take first pending
                                    if item.label.lower() in record_name.lower() or record_name.lower() in item.label.lower():
                                        batch_manifest.mark_completed(item.ref, str(record["id"]))
                                        break
                            else:
                                # No match found, mark first pending item
                                pending_items = [i for i in batch_manifest.items if i.status == "pending"]
                                if pending_items:
                                    batch_manifest.mark_completed(pending_items[0].ref, str(record["id"]))
                elif isinstance(result, dict) and result.get("id"):
                    # Single record created
                    pending_items = [i for i in batch_manifest.items if i.status == "pending"]
                    if pending_items:
                        batch_manifest.mark_completed(pending_items[0].ref, str(result["id"]))
                
                updated_batch_manifest = batch_manifest.model_dump()

            # Return ToolCallAction - will loop back for more operations
            action = ToolCallAction(
                tool=decision.tool,
                params=decision.params,
            )

            state_update = {
                "pending_action": action,
                "current_step_tool_results": new_tool_results,
                "id_registry": session_registry.to_dict(),  # V4 CONSOLIDATION: Single source
                # Note: NO step_index increment - step continues
            }
            
            if updated_batch_manifest:
                state_update["current_batch_manifest"] = updated_batch_manifest
            
            return state_update

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
        # V4: Batch validation - cannot complete step with pending items
        batch_manifest_data = state.get("current_batch_manifest")
        batch_progress = None
        if batch_manifest_data:
            batch_manifest = BatchManifest(**batch_manifest_data)
            
            # Check for pending items
            if batch_manifest.pending_count > 0:
                pending_refs = [item.ref for item in batch_manifest.items if item.status == "pending"]
                logger.warning(f"Act: Step complete called with {batch_manifest.pending_count} pending items: {pending_refs}")
                
                # Return blocked action - cannot complete with pending items
                return {
                    "pending_action": BlockedAction(
                        reason_code="PLAN_INVALID",
                        details=f"Cannot complete step: {batch_manifest.pending_count} items still pending: {pending_refs[:3]}{'...' if len(pending_refs) > 3 else ''}",
                        suggested_next="ask_user",
                    ),
                }
            
            # Create batch progress for the response
            batch_progress = BatchProgress(
                completed=batch_manifest.completed_count,
                total=batch_manifest.total,
                completed_items=[item.ref for item in batch_manifest.items if item.status == "completed"],
                failed_items=[{"ref": item.ref, "error": item.error} for item in batch_manifest.items if item.status == "failed"],
                pending_items=[item.ref for item in batch_manifest.items if item.status == "pending"],
            )
        
        # For read/write steps: keep the actual tool results (not LLM's summary)
        # For analyze/generate: use decision.data (LLM's output IS the result)
        if step_type in ("read", "write") and current_step_tool_results:
            # Preserve actual DB results - critical for later analyze steps
            step_data = current_step_tool_results
        elif decision.data is not None:
            step_data = decision.data
        else:
            step_data = current_step_tool_results
        
        # V5 FIX: Touch refs mentioned in analyze/generate output
        # This ensures they stay in "recent context" for subsequent turns
        if step_type in ("analyze", "generate") and decision.data:
            session_registry.touch_refs_from_step_data(
                data=decision.data,
                result_summary=decision.result_summary
            )
        
        # Cache the combined result for this step
        new_step_results = step_results.copy()
        new_step_results[current_step_index] = step_data

        # V4: Store step metadata with artifacts for generate/analyze steps
        # This allows write steps to access full generated content
        step_metadata = state.get("step_metadata", {}).copy()
        artifacts = None
        if step_type in ("generate", "analyze") and decision.data:
            # Extract artifacts from generate step data
            # Artifacts are the full generated content (recipes, plans, etc.)
            if isinstance(decision.data, dict):
                # If data has explicit artifacts key, use it
                if "artifacts" in decision.data:
                    artifacts = decision.data["artifacts"]
                elif "recipes" in decision.data:
                    # Common pattern: generated recipes
                    artifacts = decision.data.get("recipes", [])
                    if isinstance(artifacts, dict):
                        artifacts = [artifacts]
                elif "meal_plan" in decision.data:
                    # Generated meal plan - wrap the whole thing as one artifact
                    # The meal_plan key signals this is a meal plan structure
                    artifacts = [decision.data]
                else:
                    # Wrap entire data as single artifact
                    artifacts = [decision.data]
            elif isinstance(decision.data, list):
                artifacts = decision.data
        
        step_metadata[current_step_index] = {
            "step_type": step_type,
            "subdomain": current_step.subdomain,
            "description": current_step.description,
            "artifacts": artifacts,
        }

        # Extract note for next step (ALL step types - especially analyze!)
        note_for_next = None
        if hasattr(decision, 'note_for_next_step') and decision.note_for_next_step:
            note_for_next = decision.note_for_next_step

        action = StepCompleteAction(
            result_summary=decision.result_summary or "Step completed",
            data=step_data,
            note_for_next_step=note_for_next,
            artifacts=artifacts,
            batch_progress=batch_progress,
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

        # V4 CONSOLIDATION: Register generated artifacts in SessionIdRegistry
        # This is the ONLY place we track entities now
        if step_type == "generate" and artifacts:
            for i, artifact in enumerate(artifacts):
                if isinstance(artifact, dict):
                    entity_type = _infer_entity_type_from_artifact(artifact)
                    label = _extract_artifact_label(artifact, entity_type, i)
                    
                    # Register with SessionIdRegistry INCLUDING FULL CONTENT
                    # This is what allows "save" in a later turn to work
                    session_registry.register_generated(
                        entity_type=entity_type,
                        label=label,
                        content=artifact,
                        source_step=current_step_index,
                    )
        
        # V4 FIX: Clear archives after successful write step (pending artifacts 
        # are cleared individually by register_created when each one is promoted)
        if step_type == "write" and current_step_tool_results:
            # Check if any db_create operations succeeded
            for tool_result in current_step_tool_results:
                if len(tool_result) >= 3:
                    tool_name, subdomain, result = tool_result[:3]
                    if tool_name == "db_create" and result:
                        # NOTE: pending_artifacts are cleared individually in 
                        # SessionIdRegistry.register_created() when each gen_* ref
                        # is promoted. We don't clear ALL gen_* refs here because
                        # that would wipe unsaved artifacts (e.g., gen_recipe_2 when
                        # only gen_recipe_1 was saved).
                        
                        # Clear related archive keys (generated_recipes, etc.)
                        archive_keys_to_clear = []
                        if subdomain == "recipes":
                            archive_keys_to_clear.append("generated_recipes")
                        elif subdomain == "meal_plans":
                            archive_keys_to_clear.append("generated_meal_plan")
                        
                        for key in archive_keys_to_clear:
                            if key in new_archive:
                                del new_archive[key]
                                logger.info(f"Cleared archive key '{key}' after save")

        return {
            "pending_action": action,
            "current_step_index": current_step_index + 1,
            "step_results": new_step_results,
            "step_metadata": step_metadata,
            "current_step_tool_results": [],
            "current_batch_manifest": None,
            "id_registry": session_registry.to_dict(),  # V4 CONSOLIDATION: Single source
            "schema_requests": 0,
            "content_archive": new_archive,
            "prev_step_note": note_for_next,
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
    columns: list[str] | None = Field(default=None, description="Columns to select for read (include 'instructions' for full recipes)")
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
    
    # Normalize subdomain to canonical values (single source of truth)
    # Understand passes approximate values, Act Quick normalizes
    quick_subdomain = _normalize_subdomain(quick_subdomain)
    
    logger.info(f"Act Quick: intent='{quick_intent}', subdomain='{quick_subdomain}'")
    
    # Get schema for the subdomain
    subdomain_schema = await get_schema_with_fallback(quick_subdomain)
    
    # Build prompt using shared components
    user_id = state.get("user_id", "")
    today = date.today().isoformat()
    
    # Get user's original message - CRITICAL for data extraction
    user_message = state.get("user_message", "")
    
    # Get conversation context for session awareness
    conversation = state.get("conversation", {})
    engagement_summary = conversation.get("engagement_summary", "")
    
    # V4 CONSOLIDATION: Load SESSION ID registry FIRST - needed for entity context
    registry_data = state.get("id_registry")
    if registry_data is None:
        session_registry = SessionIdRegistry(session_id=state.get("conversation_id", ""))
    elif isinstance(registry_data, SessionIdRegistry):
        session_registry = registry_data
    else:
        session_registry = SessionIdRegistry.from_dict(registry_data)
    session_registry.set_turn(state.get("current_turn", 1))
    
    # Build entity context - SAME as regular Act
    turn_step_results = conversation.get("turn_step_results", {})
    entity_context = _build_enhanced_entity_context(
        session_registry=session_registry,
        current_step_index=0,
        current_step_results={},
        turn_step_results=turn_step_results,
    )
    
    # Build conversation context - SAME as regular Act
    conversation_section = format_full_context(
        conversation, {}, 0, ACT_CONTEXT_THRESHOLD
    )
    
    # Build user prompt using SAME builder as Act
    user_prompt = build_act_user_prompt(
        step_type="read",
        step_index=0,
        total_steps=1,
        step_description=quick_intent,
        subdomain=quick_subdomain,
        user_message=user_message,
        entity_context=entity_context,
        conversation_context=conversation_section,
        prev_turn_context="",
        prev_step_results="",
        current_step_results="",
        schema=subdomain_schema,
    )
    
    # Use same system prompt as Act read steps
    system_prompt = _get_system_prompt("read")

    try:
        # Single LLM call
        decision = await call_llm(
            response_model=ActQuickDecision,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            complexity="low",  # Quick mode uses fast model
        )
        
        logger.info(f"Act Quick: tool={decision.tool}")
        
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
        
        # Execute the tool with registry - handles all ID translation
        result = await execute_crud(
            tool=decision.tool,
            params=fixed_params,
            user_id=user_id,
            registry=session_registry,  # V4: Session registry (persists across turns)
        )
        
        logger.info(f"Act Quick: Got {len(result) if isinstance(result, list) else 1} results")
        
        # Store result for Reply (NOTE: result now contains refs, not UUIDs)
        step_results = {
            0: [(decision.tool, quick_subdomain, result)]  # Format like normal act results
        }
        
        registry_dict = session_registry.to_dict()
        logger.info(f"Act Quick: Registry has {len(session_registry.ref_to_uuid)} entities")
        
        return {
            "step_results": step_results,
            "current_step_index": 1,  # Mark as complete
            "quick_result": result,  # Direct result for Reply Quick
            "id_registry": registry_dict,  # V4 CONSOLIDATION: Single source
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
