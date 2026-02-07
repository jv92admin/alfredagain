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
    BatchProgress,
    BlockedAction,
    FailAction,
    StepCompleteAction,
    UnderstandOutput,
)
from alfred.context.builders import build_reply_context
from alfred.context.reasoning import get_reasoning_trace, format_reasoning
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import format_condensed_context


# Load prompts once at module level
_REPLY_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "reply.md"
_REPLY_PROMPT: str | None = None
_SYSTEM_PROMPT: str | None = None


def _get_prompts() -> tuple[str, str]:
    """Load the reply and system prompts, injecting domain-specific content."""
    global _REPLY_PROMPT, _SYSTEM_PROMPT
    from alfred.domain import get_current_domain
    domain = get_current_domain()

    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = domain.get_system_prompt()

    if _REPLY_PROMPT is None:
        raw = _REPLY_PROMPT_PATH.read_text(encoding="utf-8")
        # Inject domain-specific subdomain formatting guide
        subdomain_guide = domain.get_reply_subdomain_guide()
        _REPLY_PROMPT = raw.replace("{domain_subdomain_guide}", subdomain_guide)

    return _SYSTEM_PROMPT, _REPLY_PROMPT


class ReplyOutput(BaseModel):
    """The final response to the user."""
    
    response: str


# =============================================================================
# V4 Status Formatting
# =============================================================================


def _format_batch_status(batch_progress) -> str:
    """
    V4: Format batch progress for Reply.
    
    Surfaces exact status: "3 of 3 saved" or "2 of 3 saved (1 failed)"
    """
    if not batch_progress:
        return ""
    
    completed = batch_progress.completed
    total = batch_progress.total
    failed_items = batch_progress.failed_items
    
    if completed == total and not failed_items:
        return f"✅ **{completed} of {total} saved successfully**"
    
    parts = [f"**{completed} of {total} saved**"]
    
    if failed_items:
        failed_count = len(failed_items)
        parts.append(f"❌ **{failed_count} failed**")
        # Show specific failures
        for failure in failed_items[:3]:
            ref = failure.get("ref", "item")
            error = failure.get("error", "unknown error")
            parts.append(f"  - {ref}: {error}")
        if len(failed_items) > 3:
            parts.append(f"  ... and {len(failed_items) - 3} more failures")
    
    return "\n".join(parts)


def _build_conversation_flow_section(conversation: dict, current_turn: int) -> str:
    """
    V6: Build conversation flow section for Reply continuity.
    
    Tells Reply:
    - What turn we're on
    - Conversation phase (from reasoning trace)
    - What user expressed
    - Guidance for natural continuation
    """
    lines = []
    
    # Get reasoning trace for phase info
    reasoning_trace = get_reasoning_trace(conversation)
    
    # Turn counter
    if current_turn > 1:
        lines.append(f"## Conversation Flow")
        lines.append(f"**Turn:** {current_turn}")
        
        # Phase from last turn summary
        if reasoning_trace.recent_summaries:
            last_summary = reasoning_trace.recent_summaries[-1]
            if last_summary.conversation_phase:
                lines.append(f"**Phase:** {last_summary.conversation_phase}")
            if last_summary.user_expressed:
                lines.append(f"**User expressed:** {last_summary.user_expressed}")
        
        # Continuity guidance
        lines.append("")
        lines.append("**Continuity guidance:**")
        lines.append("- This is turn {}, not the start of a conversation".format(current_turn))
        lines.append("- Acknowledge naturally (\"Got it\", \"Sure\", etc.) — no \"Hello!\" or \"I'd be happy to help\"")
        lines.append("- Build on what was discussed, don't introduce yourself")
    
    return "\n".join(lines) if lines else ""


def _format_representational_status(step_results: dict, step_metadata: dict) -> str:
    """
    V4: Format representational status - what's generated vs saved.
    
    Speaks as witness: reports what actually happened, not what should have.
    """
    generated_count = 0
    saved_count = 0
    generated_items = []
    saved_items = []
    
    for step_idx, metadata in step_metadata.items():
        step_type = metadata.get("step_type")
        artifacts = metadata.get("artifacts", [])
        
        if step_type == "generate":
            generated_count += len(artifacts)
            for artifact in artifacts:
                if isinstance(artifact, dict):
                    name = artifact.get("name") or artifact.get("title") or "item"
                    generated_items.append(name)
    
    # Check step_results for actual saves (write steps)
    for step_idx, result in step_results.items():
        metadata = step_metadata.get(step_idx, {})
        if metadata.get("step_type") == "write":
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, tuple) and len(item) >= 3:
                        _tool, _table, data = item[:3]
                        if isinstance(data, list):
                            saved_count += len(data)
                            for record in data:
                                if isinstance(record, dict):
                                    name = record.get("name") or record.get("title") or "item"
                                    saved_items.append(name)
                        elif isinstance(data, dict):
                            saved_count += 1
                            name = data.get("name") or data.get("title") or "item"
                            saved_items.append(name)
    
    lines = []
    
    if generated_count > 0 and saved_count == 0:
        lines.append(f"📝 **{generated_count} items generated but NOT yet saved**")
        if generated_items:
            lines.append(f"   Generated: {', '.join(generated_items[:5])}")
        lines.append("   → Would you like me to save these?")
    elif generated_count > 0 and saved_count > 0:
        if saved_count == generated_count:
            lines.append(f"✅ **{saved_count} of {generated_count} saved successfully**")
        else:
            unsaved = generated_count - saved_count
            lines.append(f"⚠️ **{saved_count} of {generated_count} saved**")
            lines.append(f"   {unsaved} items still pending")
    elif saved_count > 0:
        lines.append(f"✅ **{saved_count} items saved**")
    
    return "\n".join(lines)


def _format_next_step_suggestion(step_results: dict, step_metadata: dict, think_output) -> str:
    """
    V4: Generate a single next-step suggestion (not multiple options).
    """
    # Check if there's unsaved generated content
    has_unsaved = False
    for step_idx, metadata in step_metadata.items():
        if metadata.get("step_type") == "generate" and metadata.get("artifacts"):
            # Check if there's a subsequent write step that saved these
            has_write = any(
                step_metadata.get(i, {}).get("step_type") == "write" 
                for i in range(step_idx + 1, max(step_metadata.keys()) + 1)
            )
            if not has_write:
                has_unsaved = True
                break
    
    if has_unsaved:
        return "💡 **Next:** Say 'save' to add these to your collection."
    
    # Check if this was a read operation
    if step_results and not step_metadata:
        return "💡 **Next:** Want me to do something with these?"
    
    # Default: no suggestion (keeps response clean)
    return ""


def _format_proposal_response(think_output) -> str:
    """
    Format a proposal response for user confirmation.
    
    If Think provided a proposal_message, use it directly.
    Otherwise build a simple presentation from assumptions.
    """
    message = getattr(think_output, "proposal_message", None)
    
    if message:
        # Think provided a message - use it as-is (it should include the ask)
        return message
    
    # Fallback: build from goal/assumptions
    goal = getattr(think_output, "goal", "your request")
    assumptions = getattr(think_output, "assumptions", None)
    
    response = f"Here's my plan for {goal}:"
    
    if assumptions:
        response += "\n\n"
        for assumption in assumptions:
            response += f"• {assumption}\n"
        response += "\nLet me know if this works for you."
    
    return response


def _format_clarification_response(think_output) -> str:
    """
    Format clarification questions for the user.
    
    If Think provided questions, present them directly.
    """
    questions = getattr(think_output, "clarification_questions", None)
    
    if not questions:
        # Fallback if no questions provided
        goal = getattr(think_output, "goal", "your request")
        return f"Before I proceed with {goal}, could you tell me a bit more?"
    
    if len(questions) == 1:
        # Single question - use it directly
        return questions[0]
    
    # Multiple questions - simple list
    response = "A few quick questions:\n\n"
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


def _format_quick_response(intent: str, subdomain: str, result: Any) -> str | None:
    """
    Format response without LLM for simple patterns.

    Returns None if no formatter matches (triggers LLM fallback).
    """
    from alfred.domain import get_current_domain
    domain = get_current_domain()

    # Handle empty results
    if not result or (isinstance(result, list) and len(result) == 0):
        return domain.get_empty_response(subdomain)

    # Format based on subdomain and result type
    if isinstance(result, list):
        count = len(result)

        # List display for read operations — delegate to domain formatters
        formatters = domain.get_subdomain_formatters()
        if subdomain in formatters:
            return formatters[subdomain](result)

        # Write confirmations — delegate to domain
        confirmation = domain.get_quick_write_confirmation(subdomain, count, intent)
        if confirmation:
            return confirmation

    # No formatter matched
    return None


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
    
    from alfred.domain import get_current_domain
    domain = get_current_domain()
    system_prompt = f"""{domain.get_system_prompt()}
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
        # Build prior-turn context from turn_summaries
        prior_turn_section = ""
        turn_summaries = conversation.get("turn_summaries", [])
        if turn_summaries:
            last_summary = turn_summaries[-1]
            prior_steps = last_summary.get("steps", [])
            if prior_steps:
                step_lines = [
                    f"- {s.get('description', 'Unknown step')}: {s.get('outcome', 'no outcome')}"
                    for s in prior_steps
                ]
                prior_turn_section = (
                    f"## Prior Turn Analysis (Turn {last_summary.get('turn_num', '?')})\n"
                    f"Goal: {last_summary.get('think_goal', 'unknown')}\n"
                    f"Steps completed:\n" + "\n".join(step_lines)
                )

        # Build attempted action context from structured data
        attempted_section = ""
        ctx = getattr(pending_action, "attempted_context", None)
        if ctx and isinstance(ctx, dict):
            items = ctx.get("items", [])
            items_str = ", ".join(items) if items else "unknown"
            attempted_section = (
                f"## What Was Attempted This Turn\n"
                f"Action: {ctx.get('tool', 'unknown')} on {ctx.get('table', 'unknown')}\n"
                f"Items: {items_str}"
            )

        user_prompt = f"""## Original Request
{state.get("user_message", "Unknown request")}

## Goal
{think_output.goal if think_output else "the user's request"}

{prior_turn_section}

{attempted_section}

## Status: ⚠️ Blocked (Technical Error)
Error: {pending_action.details}

{_format_execution_summary(step_results, think_output, state.get("step_metadata", {}), registry_dict=state.get("id_registry"))}

## Conversation Context
{conversation_section}

---

Report what was attempted and the technical error. Reference the prior turn's findings if relevant. Suggest retrying or an alternative approach."""

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
    
    # Get registry for ref enrichment
    registry_dict = state.get("id_registry")
    
    # V7: Build entity context for Reply (shows saved vs generated distinction)
    reply_context = build_reply_context(state)
    entity_context_section = reply_context.entity
    entity_section_formatted = ""
    if entity_context_section.active or entity_context_section.generated:
        from alfred.context.entity import format_entity_context
        entity_section_formatted = f"""## Entity Context (Saved vs Generated)

{format_entity_context(entity_context_section, mode="reply")}

**Key:** `item_3` = already saved (don't offer to save). `gen_item_1` = generated, not saved (offer to save).
"""
    
    # V6: Build conversation flow section for continuity
    conversation_flow_section = _build_conversation_flow_section(conversation, state.get("current_turn", 0))
    
    user_prompt = f"""## Original Request
{user_message}

## Goal
{think_output.goal if think_output else "Complete the user's request"}
{mismatch_warning}
{entity_section_formatted}
{_format_execution_summary(step_results, think_output, state.get("step_metadata", {}), registry_dict=registry_dict)}

## Conversation Context
{conversation_section}

{conversation_flow_section}

---

Generate a natural, helpful response. Lead with the outcome, be specific, be concise.
Speak as a WITNESS - report what actually happened, not what should have happened.
**If recommending a saved item (item_X), present IT — don't invent a new one or offer to save.**"""

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
    step_metadata: dict[int, dict] | None = None,
    batch_progress: BatchProgress | None = None,
    registry_dict: dict | None = None,
) -> str:
    """
    Format execution results as a structured handoff for Reply.
    
    V4 Changes:
    - Shows batch progress status first ("3 of 3 saved")
    - Shows representational status (generated vs saved)
    - Speaks as witness, not authority
    - Includes single next-step suggestion
    
    V5 Change:
    - Enriches entity refs (item_1, item_2) with labels for better Reply context

    Shows:
    - V4 status (batch, generated vs saved)
    - Plan overview (how many steps, completion status)
    - Each step's description + outcome
    - Key data in human-readable format
    - Next-step suggestion
    """
    # Build ref->label map from registry for enrichment
    ref_labels = {}
    if registry_dict:
        ref_labels = registry_dict.get("ref_labels", {})
    if not step_results:
        return "No steps were executed."
    
    # Get plan info if available
    steps = think_output.steps if think_output else []
    total_steps = len(steps)
    completed_steps = len(step_results)
    step_metadata = step_metadata or {}
    
    # Track what was generated vs saved for final summary
    generated_items: list[str] = []
    saved_items: list[str] = []
    
    lines = ["## Execution Summary"]
    
    # V4: Add batch progress status first if present
    if batch_progress:
        batch_status = _format_batch_status(batch_progress)
        if batch_status:
            lines.append("")
            lines.append(batch_status)
    
    # V4: Add representational status (generated vs saved)
    if step_metadata:
        rep_status = _format_representational_status(step_results, step_metadata)
        if rep_status:
            lines.append("")
            lines.append(rep_status)
    
    lines.append("")
    lines.append(f"Plan: {total_steps} steps | Completed: {completed_steps} | Status: {'✅ Success' if completed_steps >= total_steps else '⚠️ Partial'}")
    lines.append("")
    
    # V5: Promote last step as PRIMARY OUTPUT (this is what Reply should focus on)
    if step_results and completed_steps > 0:
        last_idx = max(step_results.keys())
        last_result = step_results[last_idx]
        last_step_type = getattr(steps[last_idx], "step_type", "read") if last_idx < len(steps) else "read"
        last_desc = steps[last_idx].description if last_idx < len(steps) else "Final step"
        
        # Only promote analyze/generate as primary output (reads are supporting data)
        if last_step_type in ("analyze", "generate"):
            lines.append("## 🎯 PRIMARY OUTPUT (focus on this)")
            lines.append(f"**{last_desc}** ({last_step_type})")
            lines.append("")
            if isinstance(last_result, dict):
                lines.append(_format_dict_for_reply(last_result, last_step_type, ref_labels=ref_labels))
            elif isinstance(last_result, str):
                lines.append(last_result[:2000])
            else:
                lines.append(str(last_result)[:1000])
            lines.append("")
            lines.append("---")
            lines.append("")
    
    # Show full plan if partial completion (so Reply knows what was skipped)
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
        
        # V7.1: Determine actual CRUD operation from step results
        # step_results format: [(tool, table, data), ...]
        actual_tool = None
        if isinstance(result, list) and result and isinstance(result[0], tuple) and len(result[0]) >= 1:
            actual_tool = result[0][0]  # e.g., "db_create", "db_update", "db_delete", "db_read"
        
        # Use clear labels - prefer actual tool for write steps
        if step_type == "write" and actual_tool:
            type_label = {
                "db_create": "db_create (SAVED)",
                "db_update": "db_update (SAVED)",
                "db_delete": "db_delete (SAVED)",
            }.get(actual_tool, "write (SAVED)")
        else:
            type_label = {
                "generate": "generate (NOT YET SAVED)",
                "write": "write (SAVED)",
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
                elif step_type == "read":
                    # Read step returned a single record
                    if "name" in result:
                        lines.append(f"Outcome: Found '{result.get('name')}'")
                    else:
                        lines.append("Outcome: Found 1 record")
                else:
                    lines.append("Outcome: Completed")
                # Format dict as human-readable, stripping IDs, enriching refs
                lines.append(_format_dict_for_reply(result, step_type, ref_labels=ref_labels))
        
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
    
    # V4: Add single next-step suggestion
    next_step = _format_next_step_suggestion(step_results, step_metadata, think_output)
    if next_step:
        lines.append("")
        lines.append(next_step)
    
    return "\n".join(lines)


def _track_items_from_dict(result: dict, items_list: list[str]) -> None:
    """Extract item names from a dict result and add to tracking list."""
    from alfred.domain import get_current_domain
    domain = get_current_domain()
    tracking_keys = domain.get_item_tracking_keys()
    for key in tracking_keys:
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

def _get_strip_fields() -> set[str]:
    """Get fields to strip from records for reply display."""
    from alfred.domain import get_current_domain
    return get_current_domain().get_strip_fields("reply")


def _clean_record(record: dict) -> dict:
    """Strip internal fields from a record, keep human-readable ones."""
    strip_fields = _get_strip_fields()
    return {k: v for k, v in record.items()
            if k not in strip_fields and v is not None}


def _detect_table_type(record: dict) -> str | None:
    """Detect table type from record structure. Delegates to domain."""
    from alfred.domain import get_current_domain
    return get_current_domain().infer_table_from_record(record)


def _format_items_for_reply(items: list, max_items: int = 50, indent: int = 2) -> str:
    """
    Format a list of items for Reply in human-readable format.

    Strips IDs, keeps names/quantities/dates/notes.
    Delegates domain-specific formatting (preferences, etc.) to domain config.

    Args:
        items: List of records to format
        max_items: Maximum items to show
        indent: Number of spaces for indentation
    """
    if not items:
        prefix = " " * indent
        return f"{prefix}(none)"

    prefix = " " * indent

    # Detect table type from first record
    first_record = items[0] if items and isinstance(items[0], dict) else {}
    table_type = _detect_table_type(first_record)

    # Try domain-specific formatting first
    from alfred.domain import get_current_domain
    domain = get_current_domain()
    domain_formatted = domain.format_records_for_reply(
        items[:max_items], table_type, indent
    )
    if domain_formatted is not None:
        if len(items) > max_items:
            domain_formatted += f"\n{prefix}... and {len(items) - max_items} more"
        return domain_formatted

    # Generic formatting fallback
    lines = []
    for item in items[:max_items]:
        if isinstance(item, dict):
            clean = _clean_record(item)
            name = (clean.get("name") or clean.get("title") or clean.get("date") or
                    clean.get("description", "")[:50] or
                    f"({table_type or 'record'} updated)")
            parts = [f"{prefix}- {name}"]

            # Generic field display
            if clean.get("quantity"):
                unit = clean.get("unit", "")
                parts.append(f"({clean['quantity']} {unit})" if unit else f"({clean['quantity']})")
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


def _format_dict_for_reply(data: dict, step_type: str, max_chars: int = 8000, ref_labels: dict | None = None) -> str:
    """
    Format a dict result for Reply in human-readable format.
    
    For analyze/generate steps, preserves structure but strips IDs.
    For CRUD, extracts key human-readable fields.
    
    V5: Enriches entity refs (item_1, item_2) with labels from registry.
    """
    import json
    import re
    
    ref_labels = ref_labels or {}
    
    def _enrich_ref(value: str) -> str:
        """Enrich a ref like 'item_1' with its label if available."""
        if not isinstance(value, str):
            return value
        # Check if it looks like a ref (entity_N pattern)
        if re.match(r'^[a-z]+_\d+$', value):
            label = ref_labels.get(value)
            if label and label != value:
                return f"{value} ({label})"
        return value
    
    strip_fields = _get_strip_fields()

    def _clean_nested(obj):
        """Recursively clean nested data structures and enrich refs."""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k not in strip_fields and v is not None:
                    cleaned[k] = _clean_nested(v)
            return cleaned
        elif isinstance(obj, list):
            return [_clean_nested(item) for item in obj]
        elif isinstance(obj, str):
            return _enrich_ref(obj)
        else:
            return obj
    
    # Clean the data and enrich refs
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
            # Single record - label based on step type
            name = clean_data.get("name") or clean_data.get("title", "record")
            if step_type == "read":
                parts = [f"  {name}"]  # Just the name for reads
            elif step_type == "write":
                parts = [f"  Saved: {name}"]
            else:
                parts = [f"  {name}"]
            from alfred.domain import get_current_domain as _gcd
            priority_fields = _gcd().get_priority_fields()
            for field in priority_fields:
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
