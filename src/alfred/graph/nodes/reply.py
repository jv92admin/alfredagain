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
    error = state.get("error")
    conversation = state.get("conversation", {})
    
    # Format conversation context (condensed for Reply)
    conversation_section = format_condensed_context(conversation)
    
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
    
    # Normal completion - generate response from results
    user_prompt = f"""## Original Request
{state.get("user_message", "Unknown request")}

## Goal
{think_output.goal if think_output else "Complete the user's request"}

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
    
    lines = [
        "## Execution Summary",
        f"Plan: {total_steps} steps | Completed: {completed_steps} | Status: {'✅ Success' if completed_steps >= total_steps else '⚠️ Partial'}",
        "",
    ]
    
    # Format each step with its description and outcome
    for idx in sorted(step_results.keys()):
        result = step_results[idx]
        
        # Get step description from plan
        step_desc = steps[idx].description if idx < len(steps) else f"Step {idx + 1}"
        step_type = getattr(steps[idx], "step_type", "crud") if idx < len(steps) else "crud"
        
        lines.append(f"### Step {idx + 1}: {step_desc}")
        lines.append(f"Type: {step_type}")
        
        # Format the outcome - Reply needs accuracy but NOT raw IDs/schema
        # Strip internal fields, keep human-readable content
        
        if isinstance(result, list):
            if len(result) == 0:
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
                    lines.append("Outcome: Content generated")
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
    
    return "\n".join(lines)


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


def _format_items_for_reply(items: list, max_items: int = 50) -> str:
    """
    Format a list of items for Reply in human-readable format.
    
    Strips IDs, keeps names/quantities/dates/notes.
    """
    if not items:
        return "  (none)"
    
    lines = []
    for item in items[:max_items]:
        if isinstance(item, dict):
            clean = _clean_record(item)
            
            # Build human-readable line
            name = clean.get("name") or clean.get("title") or clean.get("date", "item")
            parts = [f"  - {name}"]
            
            # Add key details
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
            lines.append(f"  - {item}")
    
    if len(items) > max_items:
        lines.append(f"  ... and {len(items) - max_items} more")
    
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
