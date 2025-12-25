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


async def reply_node(state: AlfredState) -> dict:
    """
    Reply node - generates final user response.
    
    Synthesizes execution results into a natural, helpful response.
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
    
    # Handle special cases
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

    result = await call_llm(
        response_model=ReplyOutput,
        system_prompt=full_system_prompt,
        user_prompt=user_prompt,
        complexity="low",  # Reply generation is straightforward
    )
    
    return {"final_response": result.response}


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
        
        # Format the outcome
        if isinstance(result, list):
            if len(result) == 0:
                lines.append("Outcome: No records found")
            else:
                lines.append(f"Outcome: Found {len(result)} items")
                # Show items with key details
                for item in result:
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
        
        elif isinstance(result, dict):
            # Single record created/updated or structured analysis
            if "deleted" in result:
                # Deletion result - handle both list and count formats
                deleted = result.get("deleted", [])
                remaining = result.get("remaining", [])
                if isinstance(deleted, int):
                    # LLM returned count instead of list
                    lines.append(f"Outcome: Deleted {deleted} items")
                elif isinstance(deleted, list) and deleted:
                    lines.append(f"Outcome: Deleted {len(deleted)} items ({', '.join(str(d) for d in deleted)})")
                else:
                    lines.append("Outcome: Nothing to delete (already empty)")
                if remaining and isinstance(remaining, list):
                    lines.append(f"Remaining: {', '.join(str(r) for r in remaining)}")
            elif _has_single_list_value(result):
                # Wrapped list result ({"any_key": [...]}) - unwrap and format
                key, items = _get_single_list_value(result)
                lines.extend(_format_item_list(items, label=key))
            elif "name" in result:
                # Created record
                name = result.get("name", "record")
                lines.append(f"Outcome: Created/Updated '{name}'")
                for key in ["cuisine", "difficulty", "servings", "quantity", "unit"]:
                    if key in result and result[key]:
                        lines.append(f"  {key}: {result[key]}")
            else:
                # Generic dict (analysis result, generated content)
                lines.append(f"Outcome: {_summarize_dict(result)}")
        
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
