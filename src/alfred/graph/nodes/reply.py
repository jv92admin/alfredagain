"""
Alfred V2 - Reply Node.

The Reply node synthesizes the final response to the user
based on execution results.

Now includes conversation context for continuity awareness.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from alfred.graph.state import (
    AlfredState,
    AskUserAction,
    BlockedAction,
    FailAction,
    StepCompleteAction,
    UnderstandOutput,
)
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context


# Load prompts once at module level
_REPLY_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "reply.md"
_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "system.md"
_REPLY_PROMPT: str | None = None
_SYSTEM_PROMPT: str | None = None


def _get_prompts() -> tuple[str, str]:
    """Load the reply and system prompts."""
    global _REPLY_PROMPT, _SYSTEM_PROMPT
    
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    
    if _REPLY_PROMPT is None:
        _REPLY_PROMPT = _REPLY_PROMPT_PATH.read_text(encoding="utf-8")
    
    return _SYSTEM_PROMPT, _REPLY_PROMPT


class ReplyOutput(BaseModel):
    """The final response to the user."""
    
    response: str


def _format_proposal_response(think_output) -> str:
    """
    Format a proposal response for user confirmation.
    
    Takes Think's assumptions and presents them in a friendly,
    confirmable format.
    """
    goal = getattr(think_output, "goal", "your request")
    message = getattr(think_output, "proposal_message", None)
    assumptions = getattr(think_output, "assumptions", None)
    
    if message:
        # Think provided a nice message - use it
        response = message
    else:
        # Build from assumptions
        response = f"Here's my plan for {goal}:"
        
        if assumptions:
            response += "\n\n"
            for assumption in assumptions:
                response += f"• {assumption}\n"
    
    # Add confirmation prompt
    response += "\n\nSound good? (You can confirm, adjust, or tell me more details.)"
    
    return response


def _format_clarification_response(think_output) -> str:
    """
    Format clarification questions for the user.
    
    Presents questions in a friendly, non-interrogative way.
    """
    goal = getattr(think_output, "goal", "your request")
    questions = getattr(think_output, "clarification_questions", None)
    
    if not questions:
        return f"I'd like to help with {goal}, but I need a bit more information. Could you tell me more about what you're looking for?"
    
    if len(questions) == 1:
        # Single question - keep it simple
        return questions[0]
    
    # Multiple questions - format as a friendly list
    response = f"I'd love to help with {goal}! A few quick questions:\n\n"
    
    for i, question in enumerate(questions, 1):
        response += f"{i}. {question}\n"
    
    return response


def _format_understand_clarification(understand_output) -> str:
    """
    Format Understand's clarification questions for the user.
    
    V3: Understand may need clarification before Think can plan.
    This handles ambiguous references, missing context, etc.
    """
    questions = getattr(understand_output, "clarification_questions", None)
    reason = getattr(understand_output, "clarification_reason", None)
    processed = getattr(understand_output, "processed_message", "")
    
    if not questions:
        # Fallback if no questions provided
        return "I'd like to help, but I need a bit more context. Could you tell me more about what you're looking for?"
    
    if len(questions) == 1:
        # Single question - keep it conversational
        return questions[0]
    
    # Multiple questions
    response = "Before I proceed, I have a few questions:\n\n"
    for i, question in enumerate(questions, 1):
        response += f"{i}. {question}\n"
    
    return response


# =============================================================================
# Phase 4: Quick Mode Formatters
# =============================================================================


# Empty result responses by subdomain
EMPTY_RESPONSES = {
    "inventory": "Your pantry is empty. Want me to help you add some items?",
    "shopping": "Your shopping list is empty.",
    "recipes": "No recipes saved yet. Want me to suggest some?",
    "tasks": "No tasks on your list.",
    "meal_plans": "No meal plans scheduled.",
    "preferences": "No preferences set yet.",
}


def _format_quick_response(intent: str, subdomain: str, result: Any) -> str | None:
    """
    Format response without LLM for simple patterns.
    
    Returns None if no formatter matches (triggers LLM fallback).
    """
    # Handle empty results
    if not result or (isinstance(result, list) and len(result) == 0):
        return EMPTY_RESPONSES.get(subdomain, "No results found.")
    
    # Format based on subdomain and result type
    if isinstance(result, list):
        count = len(result)
        
        # List display for read operations
        if subdomain == "inventory":
            return _format_inventory_list(result)
        elif subdomain == "recipes":
            return _format_recipe_list(result)
        elif subdomain == "shopping":
            return _format_shopping_list(result)
        elif subdomain == "tasks":
            return _format_task_list(result)
        elif subdomain == "meal_plans":
            return _format_meal_plan_list(result)
        
        # Write confirmations
        intent_lower = intent.lower()
        if "add" in intent_lower or "create" in intent_lower:
            item_word = "item" if count == 1 else "items"
            if subdomain == "shopping":
                return f"Added {count} {item_word} to your shopping list."
            elif subdomain == "inventory":
                return f"Added {count} {item_word} to your pantry."
            elif subdomain == "tasks":
                return f"Added {count} task{'s' if count > 1 else ''}."
        
        if "delete" in intent_lower or "remove" in intent_lower or "clear" in intent_lower:
            item_word = "item" if count == 1 else "items"
            return f"Removed {count} {item_word}."
    
    # No formatter matched
    return None


def _format_inventory_list(items: list) -> str:
    """Format inventory items for display."""
    if not items:
        return EMPTY_RESPONSES["inventory"]
    
    lines = ["Here's what's in your pantry:\n"]
    
    # Group by location if available
    by_location: dict[str, list] = {}
    for item in items:
        loc = item.get("location", "other") or "other"
        if loc not in by_location:
            by_location[loc] = []
        by_location[loc].append(item)
    
    for location, loc_items in by_location.items():
        if len(by_location) > 1:
            lines.append(f"\n**{location.title()}:**")
        for item in loc_items:
            name = item.get("name", "Unknown")
            qty = item.get("quantity", "")
            unit = item.get("unit", "")
            qty_str = f" ({qty} {unit})" if qty else ""
            lines.append(f"- {name}{qty_str}")
    
    return "\n".join(lines)


def _format_recipe_list(recipes: list) -> str:
    """Format recipe list for display."""
    if not recipes:
        return EMPTY_RESPONSES["recipes"]
    
    lines = [f"You have {len(recipes)} recipe{'s' if len(recipes) > 1 else ''} saved:\n"]
    
    for recipe in recipes[:20]:  # Limit display
        name = recipe.get("name", "Untitled")
        cuisine = recipe.get("cuisine", "")
        cuisine_str = f" ({cuisine})" if cuisine else ""
        lines.append(f"- **{name}**{cuisine_str}")
    
    if len(recipes) > 20:
        lines.append(f"\n...and {len(recipes) - 20} more.")
    
    return "\n".join(lines)


def _format_shopping_list(items: list) -> str:
    """Format shopping list for display."""
    if not items:
        return EMPTY_RESPONSES["shopping"]
    
    lines = [f"Your shopping list ({len(items)} item{'s' if len(items) > 1 else ''}):\n"]
    
    for item in items:
        name = item.get("name", "Unknown")
        qty = item.get("quantity", "")
        unit = item.get("unit", "")
        qty_str = f" ({qty} {unit})" if qty else ""
        checked = "☑" if item.get("checked") else "☐"
        lines.append(f"{checked} {name}{qty_str}")
    
    return "\n".join(lines)


def _format_task_list(tasks: list) -> str:
    """Format task list for display."""
    if not tasks:
        return EMPTY_RESPONSES["tasks"]
    
    lines = [f"Your tasks ({len(tasks)}):\n"]
    
    for task in tasks:
        desc = task.get("description", "No description")
        done = "✓" if task.get("completed") else "○"
        lines.append(f"{done} {desc}")
    
    return "\n".join(lines)


def _format_meal_plan_list(plans: list) -> str:
    """Format meal plan list for display."""
    if not plans:
        return EMPTY_RESPONSES["meal_plans"]
    
    lines = [f"Your meal plans ({len(plans)} scheduled):\n"]
    
    # Group by date
    by_date: dict[str, list] = {}
    for plan in plans:
        date = plan.get("date", "Unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(plan)
    
    for date, date_plans in sorted(by_date.items()):
        lines.append(f"\n**{date}:**")
        for plan in date_plans:
            meal_type = plan.get("meal_type", "meal")
            notes = plan.get("notes", "")
            lines.append(f"- {meal_type.title()}: {notes or '(no details)'}")
    
    return "\n".join(lines)


async def _quick_llm_response(
    user_message: str,
    intent: str,
    subdomain: str,
    result: Any,
    action_performed: str = "read",  # What action was ACTUALLY done
) -> str:
    """
    Light LLM call for quick mode when deterministic formatter doesn't match.
    
    Uses minimal prompt for fast response.
    """
    # Count results
    if isinstance(result, list):
        count = len(result)
        result_summary = f"{count} record{'s' if count != 1 else ''}"
    else:
        result_summary = "1 record"
    
    # Detect intent/action mismatch
    intent_lower = intent.lower()
    expected_action = "read"
    if any(verb in intent_lower for verb in ["update", "change", "modify", "set"]):
        expected_action = "update"
    elif any(verb in intent_lower for verb in ["add", "create", "insert", "save"]):
        expected_action = "create"
    elif any(verb in intent_lower for verb in ["delete", "remove", "clear"]):
        expected_action = "delete"
    
    mismatch_warning = ""
    if expected_action != action_performed:
        mismatch_warning = f"""
⚠️ IMPORTANT: The user wanted to {expected_action.upper()} but we only {action_performed.upper()}ed.
Do NOT claim you completed the {expected_action}. Be honest that you only read the data."""
    
    system_prompt = """You are Alfred, a helpful kitchen assistant. 
Give a brief, friendly response based on the results. Be concise.
NEVER claim to have updated/created/deleted something if you only read data."""
    
    user_prompt = f"""User asked: "{user_message}"
Intent: {intent}
Subdomain: {subdomain}
Action performed: {action_performed.upper()}
Result: {result_summary}
{mismatch_warning}

Respond naturally in 1-2 sentences. Be honest about what action was taken."""
    
    try:
        output = await call_llm(
            response_model=ReplyOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            complexity="low",
        )
        return output.response
    except Exception:
        # Ultimate fallback
        return f"Done! {result_summary} processed."


async def reply_node(state: AlfredState) -> dict:
    """
    Reply node - generates final user response.
    
    Handles three modes:
    1. Normal completion: Synthesize execution results
    2. Propose mode: Present assumptions for user confirmation
    3. Clarify mode: Ask clarifying questions
    
    Now includes conversation context for continuity awareness.
    
    Args:
        state: Current graph state with step_results and any errors
        
    Returns:
        State update with final_response
    """
    # Set node name for prompt logging
    set_current_node("reply")

    system_prompt, reply_instructions = _get_prompts()
    
    # Combine system prompt with reply instructions
    full_system_prompt = f"{system_prompt}\n\n---\n\n{reply_instructions}"
    
    # Build context for the reply
    step_results = state.get("step_results", {})
    pending_action = state.get("pending_action")
    think_output = state.get("think_output")
    understand_output = state.get("understand_output")
    error = state.get("error")
    conversation = state.get("conversation", {})
    
    # Format conversation context (condensed for Reply)
    conversation_section = format_condensed_context(conversation)
    
    # =========================================================================
    # V3: Handle Understand clarification - MUST check this first
    # =========================================================================
    
    if understand_output and getattr(understand_output, "needs_clarification", False):
        # Understand needs clarification - format and return the questions
        response = _format_understand_clarification(understand_output)
        return {"final_response": response}
    
    # =========================================================================
    # Phase 4: Quick mode - deterministic or light LLM response
    # =========================================================================
    
    quick_result = state.get("quick_result")
    if quick_result is not None and understand_output:
        quick_intent = getattr(understand_output, "quick_intent", "")
        quick_subdomain = getattr(understand_output, "quick_subdomain", "")
        
        # Determine what action was actually performed from step_results
        action_performed = "read"  # Default
        if step_results:
            # Step results format: {0: [(tool, subdomain, data), ...]}
            first_result = step_results.get(0, [])
            if first_result and isinstance(first_result, list) and first_result:
                if isinstance(first_result[0], tuple) and len(first_result[0]) >= 1:
                    tool = first_result[0][0]
                    action_performed = {
                        "db_read": "read",
                        "db_create": "create",
                        "db_update": "update",
                        "db_delete": "delete",
                    }.get(tool, "read")
        
        # Try deterministic formatter first
        response = _format_quick_response(quick_intent, quick_subdomain, quick_result)
        if response:
            return {"final_response": response}
        
        # Fallback: light LLM call with action mismatch detection
        response = await _quick_llm_response(
            state.get("user_message", ""),
            quick_intent,
            quick_subdomain,
            quick_result,
            action_performed,
        )
        return {"final_response": response}
    
    # =========================================================================
    # Handle Think decision modes (propose/clarify) - skip execution
    # =========================================================================
    
    if think_output and hasattr(think_output, "decision"):
        decision = think_output.decision
        
        if decision == "propose":
            # Format the proposal nicely for user confirmation
            response = _format_proposal_response(think_output)
            return {"final_response": response}
        
        elif decision == "clarify":
            # Format the clarification questions
            response = _format_clarification_response(think_output)
            return {"final_response": response}
    
    # =========================================================================
    # Handle error cases
    # =========================================================================
    
    if error:
        return {
            "final_response": f"I'm sorry, something went wrong: {error}"
        }
    
    # Handle ask_user - just pass through the question
    if isinstance(pending_action, AskUserAction):
        return {
            "final_response": f"{pending_action.question}\n\n({pending_action.context})"
        }
    
    # Handle fail
    if isinstance(pending_action, FailAction):
        return {
            "final_response": pending_action.user_message
        }
    
    # Handle blocked
    if isinstance(pending_action, BlockedAction):
        # Generate a helpful response about being blocked
        user_prompt = f"""## Original Request
{state.get("user_message", "Unknown request")}

## Goal
{think_output.goal if think_output else "the user's request"}

## Status: ⚠️ Blocked
Reason: {pending_action.details}

{_format_execution_summary(step_results, think_output)}

## Conversation Context
{conversation_section}

---

Generate a helpful response explaining what was accomplished and what we could try next."""

        result = await call_llm(
            response_model=ReplyOutput,
            system_prompt=full_system_prompt,
            user_prompt=user_prompt,
            complexity="low",
        )
        return {"final_response": result.response}
    
    # =========================================================================
    # Guard: Handle empty execution (no steps ran)
    # =========================================================================
    
    # If no steps were executed and we have think_output, something went wrong
    if not step_results and think_output:
        # Check if there's a proposal_message we can show
        proposal = getattr(think_output, "proposal_message", None)
        if proposal:
            # Think provided a proposal but no steps ran - show the proposal
            return {"final_response": proposal}
        
        # No steps and no proposal = bug in Think
        # Don't ask LLM to hallucinate - return an honest error
        import logging
        logging.getLogger("alfred.reply").warning(
            f"Empty execution: Think planned {len(think_output.steps)} steps but none ran"
        )
        return {
            "final_response": "I understood your request but couldn't complete it. "
                              "Could you try rephrasing or providing more details?"
        }
    
    # Normal completion - generate response from results
    user_message = state.get("user_message", "Unknown request")
    
    # Detect intent/action mismatch for quick mode (no think_output)
    mismatch_warning = ""
    if not think_output and step_results:
        # Check what user wanted vs what was done
        user_lower = user_message.lower()
        wanted_action = "read"
        if any(v in user_lower for v in ["update", "change", "modify", "set", "remove"]):
            wanted_action = "update"
        elif any(v in user_lower for v in ["add", "create", "insert", "save"]):
            wanted_action = "create"
        elif any(v in user_lower for v in ["delete", "clear"]):
            wanted_action = "delete"
        
        # Check what action was actually performed
        actual_action = "read"
        first_result = step_results.get(0, [])
        if first_result and isinstance(first_result, list) and first_result:
            if isinstance(first_result[0], tuple) and len(first_result[0]) >= 1:
                tool = first_result[0][0]
                actual_action = {"db_read": "read", "db_create": "create", 
                                "db_update": "update", "db_delete": "delete"}.get(tool, "read")
        
        if wanted_action != actual_action:
            mismatch_warning = f"""
## ⚠️ ACTION MISMATCH
User wanted: {wanted_action.upper()}
Actually performed: {actual_action.upper()}

Do NOT claim you {wanted_action}d anything. Be honest that you only {actual_action} the data.
If the user wanted an update but you only read, explain that the update didn't happen.
"""
    
    user_prompt = f"""## Original Request
{user_message}

## Goal
{think_output.goal if think_output else "Complete the user's request"}
{mismatch_warning}
{_format_execution_summary(step_results, think_output)}

## Conversation Context
{conversation_section}

---

Generate a natural, helpful response. Lead with the outcome, be specific, be concise."""

    try:
        result = await call_llm(
            response_model=ReplyOutput,
            system_prompt=full_system_prompt,
            user_prompt=user_prompt,
            complexity="low",  # Reply generation is straightforward
        )
        return {"final_response": result.response}
    except Exception as e:
        # Fallback: if Reply LLM fails, generate a basic response from step results
        import logging
        logging.getLogger("alfred.reply").exception("Reply LLM call failed")
        
        # Build a basic response from what we know
        if step_results:
            basic_response = f"I completed the requested steps. {len(step_results)} step(s) were executed."
        else:
            basic_response = "I processed your request but encountered an issue generating the response."
        
        return {"final_response": basic_response}


def _format_execution_summary(
    step_results: dict[int, Any],
    think_output: Any,
) -> str:
    """
    Format execution results as a structured handoff for Reply.
    
    Shows:
    - Plan overview (how many steps, completion status)
    - Each step's description + outcome
    - Key data in human-readable format
    """
    if not step_results:
        return "No steps were executed."
    
    # Get plan info if available
    steps = think_output.steps if think_output else []
    total_steps = len(steps)
    completed_steps = len(step_results)
    
    # Track what was generated vs saved for final summary
    generated_items: list[str] = []
    saved_items: list[str] = []
    
    lines = [
        "## Execution Summary",
        f"Plan: {total_steps} steps | Completed: {completed_steps} | Status: {'✅ Success' if completed_steps >= total_steps else '⚠️ Partial'}",
        "",
    ]
    
    # Show full plan if partial completion (so Reply knows what was skipped)
    if completed_steps < total_steps and steps:
        lines.append("**Planned steps:**")
        for i, step in enumerate(steps):
            status = "✅" if i in step_results else "⏭️ skipped"
            lines.append(f"  {i + 1}. {step.description} ({status})")
        lines.append("")
    
    # Format each step with its description and outcome
    for idx in sorted(step_results.keys()):
        result = step_results[idx]
        
        # Get step details from plan
        step_desc = steps[idx].description if idx < len(steps) else f"Step {idx + 1}"
        step_type = getattr(steps[idx], "step_type", "read") if idx < len(steps) else "read"
        step_subdomain = getattr(steps[idx], "subdomain", None) if idx < len(steps) else None
        
        # Use clear labels for generate vs write
        type_label = {
            "generate": "generate (NOT YET SAVED)",
            "write": "write (SAVED TO DATABASE)",
            "read": "read",
            "analyze": "analyze",
        }.get(step_type, step_type)
        
        lines.append(f"### Step {idx + 1}: {step_desc}")
        subdomain_str = f" | Subdomain: {step_subdomain}" if step_subdomain else ""
        lines.append(f"Type: {type_label}{subdomain_str}")
        
        # Format the outcome - Reply needs accuracy but NOT raw IDs/schema
        # Strip internal fields, keep human-readable content
        
        if isinstance(result, list):
            # Check if this is a list of tool call tuples: [(tool, table, data), ...]
            # vs a list of actual records: [{"id": ..., "name": ...}, ...]
            if result and isinstance(result[0], tuple) and len(result[0]) >= 3:
                # It's tool call tuples - group by table for clarity
                records_by_table: dict[str, list] = {}
                for item in result:
                    if len(item) >= 3:
                        _tool, table, data = item[0], item[1], item[2]
                        if table not in records_by_table:
                            records_by_table[table] = []
                        if isinstance(data, list):
                            records_by_table[table].extend(data)
                        elif isinstance(data, dict):
                            records_by_table[table].append(data)
                
                total_records = sum(len(recs) for recs in records_by_table.values())
                
                # Track items for write steps
                if step_type == "write":
                    for recs in records_by_table.values():
                        _track_items_from_records(recs, saved_items)
                
                if total_records == 0:
                    lines.append("Outcome: No records found")
                elif len(records_by_table) == 1:
                    # Single table - simple format
                    table_name = list(records_by_table.keys())[0]
                    records = records_by_table[table_name]
                    outcome_verb = "✅ SAVED" if step_type == "write" else "Found"
                    lines.append(f"Outcome: {outcome_verb} {len(records)} {table_name}")
                    lines.append(_format_items_for_reply(records))
                else:
                    # Multiple tables - show per-table breakdown
                    outcome_verb = "✅ SAVED" if step_type == "write" else "Found"
                    lines.append(f"Outcome: {outcome_verb} records from {len(records_by_table)} tables")
                    for table_name, records in records_by_table.items():
                        lines.append(f"  **{table_name}**: {len(records)} records")
                        lines.append(_format_items_for_reply(records, indent=4))
            elif len(result) == 0:
                lines.append("Outcome: No records found")
            else:
                lines.append(f"Outcome: Found {len(result)} items")
                # Format as human-readable list, not raw JSON
                lines.append(_format_items_for_reply(result))
        
        elif isinstance(result, dict):
            # Single record created/updated or structured analysis
            if "deleted" in result:
                deleted = result.get("deleted", [])
                remaining = result.get("remaining", [])
                if isinstance(deleted, int):
                    lines.append(f"Outcome: Deleted {deleted} items")
                elif isinstance(deleted, list) and deleted:
                    lines.append(f"Outcome: Deleted {len(deleted)} items ({', '.join(str(d) for d in deleted[:10])})")
                else:
                    lines.append("Outcome: Nothing to delete (already empty)")
                if remaining and isinstance(remaining, list):
                    lines.append(f"Remaining: {len(remaining)} items")
            else:
                # All other dicts: analysis, generated content, created records
                if step_type == "analyze":
                    lines.append("Outcome: Analysis complete")
                elif step_type == "generate":
                    lines.append("Outcome: Content generated (NOT YET SAVED)")
                    # Track generated items
                    _track_items_from_dict(result, generated_items)
                elif step_type == "write":
                    if "name" in result:
                        name = result.get("name", "record")
                        lines.append(f"Outcome: ✅ SAVED '{name}'")
                        saved_items.append(name)
                    else:
                        lines.append("Outcome: ✅ SAVED")
                elif "name" in result:
                    lines.append(f"Outcome: Created/Updated '{result.get('name', 'record')}'")
                else:
                    lines.append("Outcome: Completed")
                # Format dict as human-readable, stripping IDs
                lines.append(_format_dict_for_reply(result, step_type))
        
        elif isinstance(result, int):
            lines.append(f"Outcome: Affected {result} records")
        
        elif isinstance(result, str):
            # Generated content
            lines.append(f"Outcome: Generated content")
            lines.append(result[:500])
        
        else:
            lines.append(f"Outcome: {str(result)[:200]}")
        
        lines.append("")
    
    # Add final summary if there's a mismatch between generated and saved
    if generated_items and saved_items:
        # Check for mismatch
        gen_set = set(generated_items)
        saved_set = set(saved_items)
        unsaved = gen_set - saved_set
        
        if unsaved:
            lines.append("---")
            lines.append("## ⚠️ Generated vs Saved Mismatch")
            lines.append(f"- **Generated**: {len(generated_items)} items ({', '.join(generated_items[:5])})")
            lines.append(f"- **Actually Saved**: {len(saved_items)} items ({', '.join(saved_items[:5])})")
            lines.append(f"- **NOT SAVED**: {', '.join(unsaved)}")
            lines.append("")
    elif generated_items and not saved_items:
        lines.append("---")
        lines.append("## 📝 Note: Content was GENERATED but NOT SAVED")
        lines.append(f"Generated items: {', '.join(generated_items[:5])}")
        lines.append("Offer to save if appropriate.")
        lines.append("")
    
    return "\n".join(lines)


def _track_items_from_dict(result: dict, items_list: list[str]) -> None:
    """Extract item names from a dict result and add to tracking list."""
    # Check for 'recipes' or similar list keys
    for key in ["recipes", "meal_plans", "tasks", "items"]:
        if key in result and isinstance(result[key], list):
            for item in result[key]:
                if isinstance(item, dict) and "name" in item:
                    items_list.append(item["name"])
    # Check for direct name
    if "name" in result:
        items_list.append(result["name"])


def _track_items_from_records(records: list, items_list: list[str]) -> None:
    """Extract item names from a list of records and add to tracking list."""
    for record in records:
        if isinstance(record, dict) and "name" in record:
            items_list.append(record["name"])


def _has_single_list_value(d: dict) -> bool:
    """Check if dict has exactly one key with a list value."""
    list_keys = [k for k, v in d.items() if isinstance(v, list)]
    return len(list_keys) == 1 and len(d) <= 2  # Allow one list + maybe a note


def _get_single_list_value(d: dict) -> tuple[str, list]:
    """Get the key and list value from a single-list dict."""
    for k, v in d.items():
        if isinstance(v, list):
            return k, v
    return "items", []


def _format_item_list(items: list, label: str = "items") -> list[str]:
    """Format a list of items for the execution summary."""
    lines = []
    if len(items) == 0:
        lines.append("Outcome: No records found")
    else:
        lines.append(f"Outcome: Found {len(items)} {label}")
        for item in items:
            if isinstance(item, dict):
                name = item.get("name", item.get("id", "item"))
                qty = item.get("quantity", "")
                unit = item.get("unit", "")
                location = item.get("location", "")
                expiry = item.get("expiry_date", "")
                
                parts = [f"  - {name}"]
                if qty and unit:
                    parts.append(f"({qty} {unit})")
                elif qty:
                    parts.append(f"({qty})")
                if location:
                    parts.append(f"[{location}]")
                if expiry:
                    parts.append(f"expires {expiry}")
                lines.append(" ".join(parts))
            else:
                lines.append(f"  - {item}")
    return lines


def _summarize_dict(d: dict) -> str:
    """Summarize a dict for display."""
    if not d:
        return "Empty result"
    
    # Try to extract key info
    summary_parts = []
    for key in ["summary", "result", "message", "content"]:
        if key in d:
            return str(d[key])[:200]
    
    # Fall back to key listing
    keys = list(d.keys())[:5]
    return f"Data with keys: {', '.join(keys)}"


# =============================================================================
# Human-Readable Formatting for Reply (strips IDs, keeps useful fields)
# =============================================================================

# Fields to strip from Reply output (internal/technical)
_STRIP_FIELDS = {"id", "user_id", "ingredient_id", "recipe_id", "meal_plan_id", 
                 "parent_recipe_id", "created_at", "updated_at", "is_purchased"}

# Fields to keep and display (human-readable)
_PRIORITY_FIELDS = ["name", "title", "date", "meal_type", "quantity", "unit", 
                    "location", "notes", "description", "instructions", "category",
                    "cuisine", "difficulty", "servings", "tags", "rating"]


def _clean_record(record: dict) -> dict:
    """Strip internal fields from a record, keep human-readable ones."""
    return {k: v for k, v in record.items() 
            if k not in _STRIP_FIELDS and v is not None}


def _detect_table_type(record: dict) -> str | None:
    """Detect table type from record structure for proper formatting."""
    if not isinstance(record, dict):
        return None
    
    # Table-specific field patterns
    if "dietary_restrictions" in record or "allergies" in record or "cooking_skill_level" in record:
        return "preferences"
    if "recipe_id" in record and "name" in record and "quantity" in record:
        return "recipe_ingredients"
    if "meal_type" in record and "date" in record:
        return "meal_plans"
    if "cuisine" in record or "prep_time" in record or "cook_time" in record or "total_time" in record:
        return "recipes"
    if "location" in record or "expiry_date" in record:
        return "inventory"
    if "is_purchased" in record:
        return "shopping_list"
    if "due_date" in record or "status" in record:
        return "tasks"
    
    return None


def _format_items_for_reply(items: list, max_items: int = 50, indent: int = 2) -> str:
    """
    Format a list of items for Reply in human-readable format.
    
    Strips IDs, keeps names/quantities/dates/notes.
    Uses table detection for special formatting (preferences, etc.)
    
    Args:
        items: List of records to format
        max_items: Maximum items to show
        indent: Number of spaces for indentation
    """
    if not items:
        prefix = " " * indent
        return f"{prefix}(none)"
    
    prefix = " " * indent
    lines = []
    
    # Detect table type from first record
    first_record = items[0] if items and isinstance(items[0], dict) else {}
    table_type = _detect_table_type(first_record)
    
    for item in items[:max_items]:
        if isinstance(item, dict):
            clean = _clean_record(item)
            
            # Special formatting for preferences (key-value pairs)
            if table_type == "preferences":
                lines.append(f"{prefix}Your Preferences:")
                for field in ["dietary_restrictions", "allergies", "favorite_cuisines", 
                              "cooking_skill_level", "available_equipment", "household_size",
                              "planning_rhythm", "current_vibes", "nutrition_goals", "disliked_ingredients"]:
                    value = clean.get(field)
                    if value is not None and value != [] and value != "":
                        label = field.replace("_", " ").title()
                        if isinstance(value, list):
                            value = ", ".join(str(v) for v in value)
                        lines.append(f"{prefix}  - {label}: {value}")
                continue
            
            # Standard formatting for other tables
            name = clean.get("name") or clean.get("title") or clean.get("date", "item")
            parts = [f"{prefix}- {name}"]
            
            # Add key details based on table type
            if table_type == "recipes":
                if clean.get("cuisine"):
                    parts.append(f"({clean['cuisine']})")
                if clean.get("total_time"):
                    parts.append(f"{clean['total_time']}min")
                if clean.get("servings"):
                    parts.append(f"serves {clean['servings']}")
                if clean.get("tags"):
                    tags = clean["tags"][:3] if isinstance(clean["tags"], list) else []
                    if tags:
                        parts.append(f"[{', '.join(tags)}]")
            elif table_type == "meal_plans":
                if clean.get("meal_type"):
                    parts.append(f"[{clean['meal_type']}]")
                if clean.get("servings"):
                    parts.append(f"({clean['servings']} servings)")
            else:
                # Generic formatting
                if clean.get("quantity"):
                    unit = clean.get("unit", "")
                    parts.append(f"({clean['quantity']} {unit})" if unit else f"({clean['quantity']})")
                if clean.get("meal_type"):
                    parts.append(f"[{clean['meal_type']}]")
                if clean.get("location"):
                    parts.append(f"[{clean['location']}]")
                if clean.get("category"):
                    parts.append(f"({clean['category']})")
            
            if clean.get("notes"):
                notes = clean["notes"][:100] + "..." if len(clean.get("notes", "")) > 100 else clean.get("notes", "")
                parts.append(f"- {notes}")
            
            lines.append(" ".join(parts))
        else:
            lines.append(f"{prefix}- {item}")
    
    if len(items) > max_items:
        lines.append(f"{prefix}... and {len(items) - max_items} more")
    
    return "\n".join(lines)


def _format_dict_for_reply(data: dict, step_type: str, max_chars: int = 8000) -> str:
    """
    Format a dict result for Reply in human-readable format.
    
    For analyze/generate steps, preserves structure but strips IDs.
    For CRUD, extracts key human-readable fields.
    """
    import json
    
    def _clean_nested(obj):
        """Recursively clean nested data structures."""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k not in _STRIP_FIELDS and v is not None:
                    cleaned[k] = _clean_nested(v)
            return cleaned
        elif isinstance(obj, list):
            return [_clean_nested(item) for item in obj]
        else:
            return obj
    
    # Clean the data
    clean_data = _clean_nested(data)
    
    # Format based on step type
    if step_type in ("analyze", "generate"):
        # For analyze/generate, include structured output but cleaned
        try:
            json_str = json.dumps(clean_data, indent=2, default=str)
            if len(json_str) > max_chars:
                json_str = json_str[:max_chars] + "\n... (truncated)"
            return f"```\n{json_str}\n```"
        except Exception:
            return str(clean_data)[:max_chars]
    else:
        # For CRUD results, format as human-readable
        if "name" in clean_data or "title" in clean_data:
            # Single record
            name = clean_data.get("name") or clean_data.get("title", "record")
            parts = [f"  Created/Updated: {name}"]
            for field in _PRIORITY_FIELDS:
                if field in clean_data and field not in ("name", "title"):
                    val = clean_data[field]
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val[:5])
                    parts.append(f"  - {field}: {val}")
            return "\n".join(parts)
        else:
            # Generic dict
            try:
                json_str = json.dumps(clean_data, indent=2, default=str)
                if len(json_str) > max_chars:
                    json_str = json_str[:max_chars] + "\n..."
                return f"```\n{json_str}\n```"
            except Exception:
                return str(clean_data)[:max_chars]
