"""
Alfred V2 - Act Node.

The Act node executes the plan step by step using generic CRUD tools.
For each step, it:
1. Gets the schema for the step's subdomain
2. Decides which CRUD operation to perform
3. Executes and caches the result

Now includes full conversation context (last 2 turns, last 2 steps full data).

Each iteration emits a structured action.
"""

from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from alfred.graph.state import (
    ACT_CONTEXT_THRESHOLD,
    FULL_DETAIL_STEPS,
    ActAction,
    AlfredState,
    AskUserAction,
    BlockedAction,
    FailAction,
    PlannedStep,
    RequestSchemaAction,
    RetrieveStepAction,
    StepCompleteAction,
    ToolCallAction,
)
from alfred.background.profile_builder import format_profile_for_prompt, get_cached_profile
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_full_context
from alfred.tools.crud import execute_crud
from alfred.tools.schema import get_schema_with_fallback


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
        if not isinstance(filters, list):
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
        if not isinstance(or_filters, list):
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

# Load prompt once at module level
_PROMPT_PATH = (
    Path(__file__).parent.parent.parent.parent.parent / "prompts" / "act.md"
)
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    """Load the act system prompt."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


def _format_step_results(step_results: dict[int, Any], current_index: int) -> str:
    """Format previous step results for context.
    
    Last FULL_DETAIL_STEPS get FULL data (essential for analyze steps).
    Older steps get summarized.
    """
    import json
    
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
        
        # Recent steps: FULL JSON data (critical for analyze steps)
        if is_recent:
            lines.append(f"**Step {step_num}**: {json.dumps(result, default=str)}")
        # Older steps: summarized
        else:
            if isinstance(result, list) and result and isinstance(result[0], tuple):
                lines.append(f"**Step {step_num}** completed with {len(result)} tool calls")
            elif isinstance(result, list):
                lines.append(f"**Step {step_num}**: {len(result)} records")
            elif isinstance(result, dict):
                # Show key facts only
                keys = list(result.keys())[:3]
                lines.append(f"**Step {step_num}**: Data with keys: {', '.join(keys)}")
            elif isinstance(result, int):
                lines.append(f"**Step {step_num}**: Affected {result} records")
            else:
                lines.append(f"**Step {step_num}**: (use retrieve_step for details)")
        
        lines.append("")

    return "\n".join(lines)


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


def _format_current_step_results(tool_results: list[tuple[str, Any]], tool_calls_made: int) -> str:
    """Format tool results from current step - show ACTUAL data, not summaries."""
    import json
    
    if not tool_results:
        return ""
    
    lines = [f"## What Already Happened This Step ({tool_calls_made} tool calls)", ""]
    
    for i, (tool_name, result) in enumerate(tool_results, 1):
        lines.append(f"### Tool Call {i}: `{tool_name}`")
        
        # Show result with semantic meaning
        if tool_name == "db_read":
            if isinstance(result, list):
                if len(result) == 0:
                    lines.append("**Result: 0 records found.**")
                    lines.append("→ Empty result. If step goal is READ: this is your answer. If step goal is ADD/CREATE: proceed with db_create.")
                elif len(result) > 50:
                    # Only truncate very large results
                    lines.append(f"**Result: {len(result)} records found.** First 50:")
                    # Add quick reference for IDs/names
                    quick_ref = _extract_key_fields(result[:50])
                    if quick_ref:
                        lines.append(quick_ref)
                        lines.append("")
                    lines.append("<details><summary>Full JSON</summary>")
                    lines.append("")
                    lines.append("```json")
                    lines.append(json.dumps(result[:50], indent=2, default=str))
                    lines.append("```")
                    lines.append("</details>")
                else:
                    # Show all records for reasonable sizes (up to 50)
                    lines.append(f"**Result: {len(result)} records found:**")
                    # Add quick reference for IDs/names FIRST
                    quick_ref = _extract_key_fields(result)
                    if quick_ref:
                        lines.append(quick_ref)
                        lines.append("")
                    lines.append("<details><summary>Full JSON</summary>")
                    lines.append("")
                    lines.append("```json")
                    lines.append(json.dumps(result, indent=2, default=str))
                    lines.append("```")
                    lines.append("</details>")
            else:
                lines.append(f"Result: `{result}`")
        elif tool_name == "db_create":
            if isinstance(result, list):
                lines.append(f"**✓ Created {len(result)} records:**")
                lines.append("```json")
                lines.append(json.dumps(result, indent=2, default=str))
                lines.append("```")
            elif isinstance(result, dict):
                lines.append(f"**✓ Created 1 record:**")
                lines.append("```json")
                lines.append(json.dumps(result, indent=2, default=str))
                lines.append("```")
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
MAX_TOOL_CALLS_PER_STEP = 5


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

    current_step: PlannedStep = steps[current_step_index]

    # Get step type (default to crud for backwards compatibility)
    step_type = getattr(current_step, "step_type", "crud")
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
        user_prompt = f"""## STATUS
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

## 2. Data Available

{prev_step_section if prev_step_section else "*No previous step data.*"}

---

## 3. Context

{conversation_section if conversation_section else "*No additional context.*"}

---

## DECISION

Analyze the data above and complete the step:
`{{"action": "step_complete", "result_summary": "Analysis: ...", "data": {{"key": "value"}}}}`"""

    elif step_type == "generate":
        user_prompt = f"""## STATUS
| Step | {current_step_index + 1} of {len(steps)} |
| Goal | {current_step.description} |
| Type | generate (create content, no db calls) |
| Today | {today} |

---

{profile_section}

## 1. Task

User said: "{state.get("user_message", "")}"

Your job this step: **{current_step.description}**

**Use the USER PROFILE above to personalize your generation:**
- Respect dietary restrictions and allergies
- Consider available equipment and time budget
- Align with nutrition goals and preferred complexity

---

## 2. Data Available

{prev_step_section if prev_step_section else "*No previous step data.*"}

---

## 3. Context

{conversation_section if conversation_section else "*No additional context.*"}

---

## DECISION

Generate the requested content and complete the step:
`{{"action": "step_complete", "result_summary": "Generated: ...", "data": {{"your_content": "here"}}}}`"""

    else:
        # CRUD step - needs schema as primary resource
        subdomain_schema = await get_schema_with_fallback(current_step.subdomain)
        
        # Build a quick status summary for the last tool call
        last_tool_summary = ""
        if current_step_tool_results:
            last_tool, last_result = current_step_tool_results[-1]
            if isinstance(last_result, list):
                last_tool_summary = f" → Last: `{last_tool}` returned {len(last_result)} records"
            elif isinstance(last_result, dict):
                last_tool_summary = f" → Last: `{last_tool}` returned 1 record"
            else:
                last_tool_summary = f" → Last: `{last_tool}` completed"
        
        user_prompt = f"""## STATUS
| Step | {current_step_index + 1} of {len(steps)} |
| Goal | {current_step.description} |
| Type | crud |
| Progress | {tool_calls_made} tool calls{last_tool_summary} |
| Today | {today} |

---

## 1. Task

User said: "{state.get("user_message", "")}"

Your job this step: **{current_step.description}**

---

## 2. Tool Results This Step

{this_step_section if this_step_section else "*No tool calls yet — make your first db_ call.*"}

---

## 3. Schema ({current_step.subdomain})

{subdomain_schema}

---

## 4. Previous Steps

{prev_step_section if prev_step_section else "*No previous steps.*"}

---

## 5. Context

{conversation_section if conversation_section else "*No additional context.*"}

---

## DECISION

What's next?
- Step done? → `{{"action": "step_complete", "result_summary": "...", "data": {{...}}}}`
- Need data? → `{{"action": "tool_call", "tool": "db_read", "params": {{"table": "...", "filters": [...], "limit": N}}}}`
- Need to create? → `{{"action": "tool_call", "tool": "db_create", "params": {{"table": "...", "data": {{...}}}}}}`"""

    # Call LLM for decision (step_results are already in the prompt)
    decision = await call_llm(
        response_model=ActDecision,
        system_prompt=_get_system_prompt(),
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
            # Store as (tool_name, result) tuple for clear formatting
            new_tool_results = current_step_tool_results + [(decision.tool, result)]

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
        # For CRUD steps: keep the actual tool results (not LLM's summary)
        # For analyze/generate: use decision.data (LLM's output IS the result)
        if step_type == "crud" and current_step_tool_results:
            # Preserve actual DB results - critical for later analyze steps
            step_data = current_step_tool_results
        elif decision.data is not None:
            step_data = decision.data
        else:
            step_data = current_step_tool_results
        
        # Cache the combined result for this step
        new_step_results = step_results.copy()
        new_step_results[current_step_index] = step_data

        action = StepCompleteAction(
            result_summary=decision.result_summary or "Step completed",
            data=step_data,
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

        return {
            "pending_action": action,
            "current_step_index": current_step_index + 1,
            "step_results": new_step_results,
            "current_step_tool_results": [],  # Reset for next step
            "schema_requests": 0,
            "content_archive": new_archive,
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
