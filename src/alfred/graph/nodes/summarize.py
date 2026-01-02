"""
Alfred V3 - Summarize Node.

The Summarize node runs after Reply to:
1. Add the current turn to conversation history
2. Merge turn_entities into entity registry
3. Garbage collect stale entities
4. Compress older turns if we exceed FULL_DETAIL_TURNS
5. Update engagement summary

V3 Changes:
- Entity lifecycle management (merge turn entities, garbage collect)
- EntityRegistry integration for state transitions
- Persist entity_registry and current_turn in conversation

This maintains conversation memory and entity lifecycle across turns.
"""

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from alfred.core.entities import Entity, EntityRegistry, EntityState
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

logger = logging.getLogger(__name__)


# =============================================================================
# Summarization Models
# =============================================================================


class TurnSummary(BaseModel):
    """LLM-generated summary of a conversation turn."""
    
    summary: str  # One sentence summary


class AssistantResponseSummary(BaseModel):
    """LLM-generated summary of an assistant response."""
    
    summary: str  # Condensed version of what was accomplished


class EngagementSummary(BaseModel):
    """LLM-generated engagement summary."""
    
    summary: str  # What we're helping with overall


# Threshold for summarizing assistant responses (characters)
SUMMARIZE_THRESHOLD = 400  # ~100 tokens


# =============================================================================
# Summarize Node
# =============================================================================


async def summarize_node(state: AlfredState) -> dict:
    """
    Summarize node - maintains conversation memory and entity lifecycle.
    
    V3 Runs after Reply to:
    1. Add current turn to history
    2. Merge turn_entities into entity registry
    3. Garbage collect stale entities
    4. Compress old turns to history_summary
    5. Compress old step results to step_summaries
    6. Update engagement summary if significant
    
    Args:
        state: Current graph state with final_response
        
    Returns:
        State update with updated conversation context and entity registry
    """
    set_current_node("summarize")
    
    user_message = state.get("user_message", "")
    final_response = state.get("final_response", "")
    router_output = state.get("router_output")
    step_results = state.get("step_results", {})
    think_output = state.get("think_output")
    conversation = state.get("conversation", {})
    current_turn_num = state.get("current_turn", 0)
    
    # Skip if no response (error case)
    if not final_response:
        return {}
    
    # 1. Create current turn (with LLM-generated summary for long responses)
    routing_info = None
    if router_output:
        routing_info = {
            "agent": router_output.agent,
            "goal": router_output.goal,
            "complexity": router_output.complexity,
        }
    
    # Detect if this was a proposal (Think decided propose/clarify, not plan_direct)
    is_proposal = False
    if think_output and hasattr(think_output, "decision"):
        is_proposal = think_output.decision in ("propose", "clarify")
    
    # Generate summary for long responses (used in conversation context)
    assistant_summary = await _summarize_assistant_response(final_response, is_proposal)
    
    current_turn = create_conversation_turn(
        user_message=user_message,
        assistant_response=final_response,
        assistant_summary=assistant_summary,  # For context formatting
        routing=routing_info,
    )
    
    # 2. V3: Merge turn_entities into entity registry
    entity_registry_data = state.get("entity_registry", {})
    registry = EntityRegistry.from_dict(entity_registry_data) if entity_registry_data else EntityRegistry()
    
    turn_entities_data = state.get("turn_entities", [])
    for te_dict in turn_entities_data:
        try:
            entity = Entity.from_dict(te_dict)
            registry.add(entity)
        except Exception as e:
            logger.warning(f"Failed to add entity to registry: {e}")
    
    # 3. V3: Garbage collect stale entities
    removed_ids = registry.garbage_collect(current_turn_num)
    if removed_ids:
        logger.info(f"Summarize: Garbage collected {len(removed_ids)} stale entities")
    
    # 4. Extract entities from step results (legacy support)
    new_entities = extract_entities_from_step_results(step_results)
    entity_refs = [EntityRef(**e.model_dump()) for e in new_entities.values()]
    
    # Also convert turn_entities to EntityRefs for legacy conversation tracking
    for te in turn_entities_data:
        entity_refs.append(EntityRef(
            type=te.get("type", "unknown"),
            id=te.get("id", ""),
            label=te.get("label", ""),
            source=te.get("source", "step_result"),
        ))
    
    # 5. Update conversation context
    content_archive = state.get("content_archive", {})
    
    updated_conversation = _update_conversation(
        conversation=conversation,
        current_turn=current_turn,
        step_results=step_results,
        think_output=think_output,
        new_entities=entity_refs,
        content_archive=content_archive,
    )
    
    # 6. Compress old turns if needed (async LLM call)
    if len(updated_conversation.get("recent_turns", [])) > FULL_DETAIL_TURNS:
        updated_conversation = await _compress_old_turns(updated_conversation)
    
    # 7. Update engagement summary if this was significant
    if _is_significant_action(router_output, step_results):
        updated_conversation = await _update_engagement_summary(
            updated_conversation, user_message, final_response
        )
    
    # 8. Track pending clarification for context threading
    if think_output and hasattr(think_output, "decision"):
        decision = think_output.decision
        if decision in ("propose", "clarify"):
            updated_conversation["pending_clarification"] = {
                "type": decision,
                "goal": getattr(think_output, "goal", ""),
                "assumptions": getattr(think_output, "assumptions", None),
                "questions": getattr(think_output, "clarification_questions", None),
                "proposal_message": getattr(think_output, "proposal_message", None),
            }
        else:
            updated_conversation["pending_clarification"] = None
    
    # Check Understand output for clarification (V3)
    understand_output = state.get("understand_output")
    if understand_output and hasattr(understand_output, "needs_clarification"):
        if understand_output.needs_clarification:
            updated_conversation["pending_clarification"] = {
                "type": "understand",
                "questions": getattr(understand_output, "clarification_questions", None),
            }
    
    # V3: Persist entity registry and current turn in conversation
    updated_conversation["entity_registry"] = registry.to_dict()
    updated_conversation["current_turn"] = current_turn_num
    
    return {
        "conversation": updated_conversation,
        "entity_registry": registry.to_dict(),  # Also update top-level for next turn
    }


def _update_conversation(
    conversation: ConversationContext,
    current_turn: dict,
    step_results: dict[int, Any],
    think_output: Any,
    new_entities: list[EntityRef],
    content_archive: dict[str, Any] | None = None,
) -> ConversationContext:
    """
    Update conversation context with new turn and entities.
    
    Does NOT compress - that's done separately with LLM.
    """
    # Merge existing and new content archive
    existing_archive = conversation.get("content_archive", {})
    merged_archive = {**existing_archive, **(content_archive or {})}
    
    updated: ConversationContext = {
        "engagement_summary": conversation.get("engagement_summary", ""),
        "recent_turns": list(conversation.get("recent_turns", [])),
        "history_summary": conversation.get("history_summary", ""),
        "step_summaries": list(conversation.get("step_summaries", [])),
        "active_entities": dict(conversation.get("active_entities", {})),
        "all_entities": dict(conversation.get("all_entities", {})),
        "content_archive": merged_archive,
    }
    
    # Add current turn
    updated["recent_turns"].append(current_turn)
    
    # Update active entities (keyed by ID, allows multiple per type)
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


def _extract_entity_names(response: str) -> list[str]:
    """
    Extract likely entity names from a response using simple patterns.
    
    Looks for:
    - **Bold headings** (common for recipe names)
    - Numbered/bulleted lists with names
    - Quoted names
    """
    import re
    names = []
    
    # Pattern 1: **Bold text** (recipe/entity names in markdown)
    bold_matches = re.findall(r'\*\*([^*]+)\*\*', response)
    for match in bold_matches:
        # Filter out common non-entity bold text
        if len(match) > 5 and len(match) < 100 and not any(skip in match.lower() for skip in 
            ['ingredient', 'instruction', 'serve', 'step', 'note', 'tip', 'prep', 'cook time']):
            names.append(match.strip())
    
    # Pattern 2: Lines starting with - or * followed by a name (bulleted lists)
    bullet_matches = re.findall(r'^[\s]*[-*]\s+([A-Z][^-\n]{10,60})(?:\s*[-–]|\s*$)', response, re.MULTILINE)
    names.extend(bullet_matches)
    
    # Pattern 3: "Name" or 'Name' in quotes
    quoted_matches = re.findall(r'["\']([A-Z][^"\']{10,60})["\']', response)
    names.extend(quoted_matches)
    
    # Dedupe while preserving order
    seen = set()
    unique_names = []
    for name in names:
        name_clean = name.strip()
        if name_clean not in seen and len(name_clean) > 5:
            seen.add(name_clean)
            unique_names.append(name_clean)
    
    return unique_names[:10]  # Cap at 10 entities


async def _summarize_assistant_response(response: str, is_proposal: bool = False) -> str:
    """
    LLM-summarize a long assistant response for conversation context.
    
    The full response is kept in the turn for Reply to use.
    The summary is used in conversation context for Act/Think.
    
    Principle: Conversation history conveys INTENT, not DATA.
    Tool results are the source of truth for specifics.
    
    CRITICAL: The summary must use EXACT entity names from the response,
    not paraphrased or generalized names. Wrong names in summaries cause
    hallucinations in subsequent turns.
    
    Args:
        response: The assistant's response text
        is_proposal: True if Think decided "propose" or "clarify" (not executed yet)
    """
    if len(response) < SUMMARIZE_THRESHOLD:
        return response  # Short enough, keep as-is
    
    # If we KNOW this is a proposal, skip LLM and use deterministic summary
    if is_proposal:
        # Extract a brief mention of what was proposed
        if "save" in response.lower():
            return "Proposed a plan and awaiting user confirmation before proceeding."
        elif "clarif" in response.lower():
            return "Asked clarifying questions before proceeding."
        else:
            return "Proposed an approach and awaiting user confirmation."
    
    # CRITICAL: Extract entity names from FULL response before truncation
    # This prevents losing entity names that appear late in long responses
    extracted_names = _extract_entity_names(response)
    names_hint = ""
    if extracted_names:
        names_hint = f"\n\n**Entities found in full text (use these EXACT names):** {', '.join(extracted_names)}"
    
    try:
        result = await call_llm(
            response_model=AssistantResponseSummary,
            system_prompt="""Summarize what was accomplished in ONE sentence.
Focus on: what action was taken, what was created/found/updated.

**CRITICAL: Proposals ≠ Completed actions**
If the text says "I'll do X" or "Here's my plan" or "Does this sound good?" — that's a PROPOSAL.
Do NOT summarize proposals as completed actions.

- Proposal: "I'll save the recipes" → Summary: "Proposed to save recipes; awaiting confirmation."
- Completed: "Done! I saved the recipes." → Summary: "Saved recipes: [names]"

**CRITICAL: Use EXACT entity names from the text.** Do NOT paraphrase or generalize.
If the text says "Mediterranean Chickpea & Herb Rice Bowl", use that EXACT name.
Do NOT make up names that sound similar but aren't in the original text.

Good: "Saved recipes: Mediterranean Chickpea & Herb Rice Bowl."
Bad: "Saved the recipes." (too vague)
Bad: "Saved Minty Chickpea Salad." (made up name not in original)
Bad: "Saved three rice bowl recipes." (when text says "I'll save" = proposal, not done)

Keep summaries specific with exact names or IDs when available.
""",
            # Include beginning (intro/outcome) + extracted names from full text
            user_prompt=f"Summarize this response using EXACT names from the text:{names_hint}\n\n{response[:2000]}",
            complexity="low",
        )
        return result.summary
    except Exception:
        # Fallback: truncate with note
        return response[:300] + "... [see step results for details]"


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
            system_prompt="""Summarize this conversation exchange in ONE brief sentence.
Focus on: what the user asked, what action was taken, any entities created/modified.

**CRITICAL: Proposals ≠ Completed actions**
If Alfred says "I'll do X" or "Here's my plan" → that's a PROPOSAL, not a completed action.
- Proposal: "I'll save the recipes" → "User requested X; assistant proposed a plan"
- Completed: "Done! I saved the recipes" → "Assistant saved recipes: [names]"

Use EXACT entity names from the text. Don't invent names.""",
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
        # Check for tuple format (tool results) - can be 2-tuple or 3-tuple
        if result and isinstance(result[0], tuple):
            total = 0
            for item in result:
                # Handle both (tool, result) and (tool, table, result) formats
                r = item[-1]  # Result is always the last element
                total += len(r) if isinstance(r, list) else 1
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
            # Handle both (tool, result) and (tool, table, result) formats
            return sum(_count_records(item[-1]) for item in result)
        return len(result)
    elif isinstance(result, dict):
        return 1
    return 0

