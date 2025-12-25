"""
Alfred V2 - Summarize Node.

The Summarize node runs after Reply to:
1. Add the current turn to conversation history
2. Extract and track entities from step results
3. Compress older turns if we exceed FULL_DETAIL_TURNS
4. Update engagement summary

This maintains conversation memory across turns.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from alfred.graph.state import (
    FULL_DETAIL_STEPS,
    FULL_DETAIL_TURNS,
    AlfredState,
    ConversationContext,
    EntityRef,
    StepSummary,
)
from alfred.llm.client import call_llm, set_current_node
from alfred.memory.conversation import (
    create_conversation_turn,
    extract_entities_from_step_results,
    update_active_entities,
)


# =============================================================================
# Summarization Models
# =============================================================================


class TurnSummary(BaseModel):
    """LLM-generated summary of a conversation turn."""
    
    summary: str  # One sentence summary


class EngagementSummary(BaseModel):
    """LLM-generated engagement summary."""
    
    summary: str  # What we're helping with overall


# =============================================================================
# Summarize Node
# =============================================================================


async def summarize_node(state: AlfredState) -> dict:
    """
    Summarize node - maintains conversation memory.
    
    Runs after Reply to:
    1. Add current turn to history
    2. Extract entities from step results
    3. Compress old turns to history_summary
    4. Compress old step results to step_summaries
    5. Update engagement summary if significant
    
    Args:
        state: Current graph state with final_response
        
    Returns:
        State update with updated conversation context
    """
    set_current_node("summarize")
    
    user_message = state.get("user_message", "")
    final_response = state.get("final_response", "")
    router_output = state.get("router_output")
    step_results = state.get("step_results", {})
    think_output = state.get("think_output")
    conversation = state.get("conversation", {})
    
    # Skip if no response (error case)
    if not final_response:
        return {}
    
    # 1. Create current turn
    routing_info = None
    if router_output:
        routing_info = {
            "agent": router_output.agent,
            "goal": router_output.goal,
            "complexity": router_output.complexity,
        }
    
    current_turn = create_conversation_turn(
        user_message=user_message,
        assistant_response=final_response,
        routing=routing_info,
    )
    
    # 2. Extract entities from step results
    new_entities = extract_entities_from_step_results(step_results)
    entity_refs = [EntityRef(**e.model_dump()) for e in new_entities.values()]
    
    # 3. Update conversation context
    updated_conversation = _update_conversation(
        conversation=conversation,
        current_turn=current_turn,
        step_results=step_results,
        think_output=think_output,
        new_entities=entity_refs,
    )
    
    # 4. Compress old turns if needed (async LLM call)
    if len(updated_conversation.get("recent_turns", [])) > FULL_DETAIL_TURNS:
        updated_conversation = await _compress_old_turns(updated_conversation)
    
    # 5. Update engagement summary if this was significant
    if _is_significant_action(router_output, step_results):
        updated_conversation = await _update_engagement_summary(
            updated_conversation, user_message, final_response
        )
    
    return {
        "conversation": updated_conversation,
    }


def _update_conversation(
    conversation: ConversationContext,
    current_turn: dict,
    step_results: dict[int, Any],
    think_output: Any,
    new_entities: list[EntityRef],
) -> ConversationContext:
    """
    Update conversation context with new turn and entities.
    
    Does NOT compress - that's done separately with LLM.
    """
    updated: ConversationContext = {
        "engagement_summary": conversation.get("engagement_summary", ""),
        "recent_turns": list(conversation.get("recent_turns", [])),
        "history_summary": conversation.get("history_summary", ""),
        "step_summaries": list(conversation.get("step_summaries", [])),
        "active_entities": dict(conversation.get("active_entities", {})),
        "all_entities": dict(conversation.get("all_entities", {})),
    }
    
    # Add current turn
    updated["recent_turns"].append(current_turn)
    
    # Update active entities (most recent of each type)
    updated["active_entities"] = update_active_entities(
        updated["active_entities"], new_entities
    )
    
    # Add to all_entities
    for entity in new_entities:
        updated["all_entities"][entity.id] = entity.model_dump()
    
    # Create step summaries for older steps
    if think_output and step_results:
        steps = think_output.steps
        for idx, result in step_results.items():
            # Only summarize steps older than FULL_DETAIL_STEPS
            if idx < len(step_results) - FULL_DETAIL_STEPS:
                # Check if we already have a summary for this step
                existing_idx = [s.get("step_index") for s in updated["step_summaries"]]
                if idx not in existing_idx:
                    step_desc = steps[idx].description if idx < len(steps) else f"Step {idx + 1}"
                    subdomain = steps[idx].subdomain if idx < len(steps) else "unknown"
                    
                    summary = StepSummary(
                        step_index=idx,
                        description=step_desc,
                        subdomain=subdomain,
                        outcome=_summarize_step_result(result),
                        entity_ids=_extract_entity_ids(result),
                        record_count=_count_records(result),
                    )
                    updated["step_summaries"].append(summary.model_dump())
    
    return updated


async def _compress_old_turns(
    conversation: ConversationContext,
) -> ConversationContext:
    """
    Compress oldest turn(s) into history_summary using LLM.
    
    Keeps last FULL_DETAIL_TURNS in full detail.
    """
    recent_turns = list(conversation.get("recent_turns", []))
    history_summary = conversation.get("history_summary", "")
    
    # Nothing to compress
    if len(recent_turns) <= FULL_DETAIL_TURNS:
        return conversation
    
    # Pop oldest turn
    oldest = recent_turns.pop(0)
    
    # Generate summary via LLM (cheap, fast model)
    user_text = oldest.get("user", "")
    assistant_text = oldest.get("assistant", "")
    
    try:
        result = await call_llm(
            response_model=TurnSummary,
            system_prompt="Summarize this conversation exchange in ONE brief sentence. Focus on: what the user asked, what action was taken, any entities created/modified.",
            user_prompt=f"User: {user_text[:500]}\nAssistant: {assistant_text[:500]}",
            complexity="low",
        )
        new_summary = result.summary
    except Exception:
        # Fallback to simple summary
        new_summary = f"User asked about something, Alfred responded."
    
    # Append to history
    if history_summary:
        updated_history = f"{history_summary} {new_summary}"
    else:
        updated_history = new_summary
    
    # Trim history if too long (keep last ~500 chars)
    if len(updated_history) > 800:
        updated_history = "..." + updated_history[-750:]
    
    return {
        **conversation,
        "recent_turns": recent_turns,
        "history_summary": updated_history,
    }


async def _update_engagement_summary(
    conversation: ConversationContext,
    user_message: str,
    assistant_response: str,
) -> ConversationContext:
    """
    Update engagement summary if this was a significant action.
    """
    current_summary = conversation.get("engagement_summary", "")
    
    try:
        result = await call_llm(
            response_model=EngagementSummary,
            system_prompt="Update the session summary to reflect what we're helping with. Keep it brief (1 sentence). Focus on the ongoing theme.",
            user_prompt=f"""Current summary: {current_summary or "New session"}

Latest exchange:
User: {user_message[:300]}
Alfred: {assistant_response[:300]}

What should the new session summary be?""",
            complexity="low",
        )
        return {
            **conversation,
            "engagement_summary": result.summary,
        }
    except Exception:
        # Keep existing summary on failure
        return conversation


def _is_significant_action(router_output: Any, step_results: dict) -> bool:
    """
    Determine if this action warrants updating engagement summary.
    
    Simple heuristic: complex actions or multi-step plans.
    """
    if not router_output:
        return False
    
    # High complexity or multi-step
    if router_output.complexity == "high":
        return True
    if len(step_results) > 2:
        return True
    
    return False


def _summarize_step_result(result: Any) -> str:
    """Create one-line summary of a step result."""
    if isinstance(result, list):
        if len(result) == 0:
            return "No records found"
        # Check for tuple format (tool results)
        if result and isinstance(result[0], tuple):
            total = sum(
                len(r) if isinstance(r, list) else 1
                for _, r in result
            )
            return f"Processed {total} records across {len(result)} operations"
        return f"Found/processed {len(result)} records"
    elif isinstance(result, dict):
        if "name" in result:
            return f"Created/updated '{result['name']}'"
        return "Processed 1 record"
    elif isinstance(result, int):
        return f"Affected {result} records"
    return "Completed"


def _extract_entity_ids(result: Any) -> list[str]:
    """Extract entity IDs from a result."""
    ids = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "id" in item:
                ids.append(str(item["id"]))
            elif isinstance(item, tuple) and len(item) == 2:
                _, tool_result = item
                ids.extend(_extract_entity_ids(tool_result))
    elif isinstance(result, dict) and "id" in result:
        ids.append(str(result["id"]))
    return ids


def _count_records(result: Any) -> int:
    """Count records in a result."""
    if isinstance(result, list):
        if result and isinstance(result[0], tuple):
            return sum(_count_records(r) for _, r in result)
        return len(result)
    elif isinstance(result, dict):
        return 1
    return 0

