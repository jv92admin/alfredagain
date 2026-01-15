"""
Alfred V4 - Summarize Node.

Summarize is the "Conversation Historian" - it records what happened.

V4 Responsibilities:
1. Append current turn to conversation history
2. Compress older turns when threshold exceeded (LLM)
3. Build SummarizeOutput (structured audit ledger, no LLM)
4. Pass through entity_context for next turn's Understand to curate

What Summarize does NOT do (V4):
- Entity curation (Understand handles this)
- Entity lifecycle management (Understand handles this)
- Engagement summary updates (Think has the goal)

The key insight: Entity relevance is intent-dependent, not time-dependent.
Understand sees the user's intent and curates accordingly.
"""

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from alfred.core.id_registry import SessionIdRegistry
from alfred.graph.state import (
    FULL_DETAIL_STEPS,
    FULL_DETAIL_TURNS,
    AlfredState,
    ConversationContext,
    EntityRef,
    StepSummary,
    TurnExecutionSummary,
    StepExecutionSummary,
    CurationSummary,
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


# =============================================================================
# V4: Structured Summarize Output
# =============================================================================


class SummarizeError(BaseModel):
    """A structured error from the turn."""
    
    code: str  # Error code ("FK_VIOLATION", "TIMEOUT", etc.)
    message: str  # Human-readable message
    step_id: int | None = None  # Which step failed


class SummarizeOutput(BaseModel):
    """
    V4: Structured audit ledger from Summarize.
    
    Produces machine-readable output, not narrative prose.
    No content generation - just factual reporting.
    """
    
    # Entity deltas (structured, not prose)
    entities_created: list[dict] = []  # [{id, type, label}]
    entities_updated: list[dict] = []  # [{id, type, label, changes}]
    entities_deleted: list[str] = []  # IDs
    
    # Artifact tracking
    artifacts_generated: dict[str, int] = {}  # {type: count} e.g., {"recipe": 3}
    artifacts_saved: dict[str, int] = {}  # {type: count}
    
    # Errors encountered
    errors: list[SummarizeError] = []
    
    # Factual turn summary (no embellishment)
    turn_summary: str = ""  # "User requested 3 recipes; 3 generated, 2 saved, 1 failed"
    
    # Metrics
    steps_completed: int = 0
    steps_total: int = 0


# Threshold for summarizing assistant responses (characters)
SUMMARIZE_THRESHOLD = 400  # ~100 tokens


# =============================================================================
# Summarize Node
# =============================================================================


async def summarize_node(state: AlfredState) -> dict:
    """
    V4 Summarize node - Conversation Historian.
    
    Responsibilities:
    1. Append current turn to conversation history
    2. Compress older turns when threshold exceeded (LLM)
    3. Build SummarizeOutput (structured audit ledger)
    4. Add new entities to context (Understand curates next turn)
    5. Track pending clarification
    
    Entity curation is NOT done here - Understand handles that.
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
    
    # ==========================================================================
    # 1. Create current turn record
    # ==========================================================================
    
    routing_info = None
    if router_output:
        routing_info = {
            "agent": router_output.agent,
            "goal": router_output.goal,
            "complexity": router_output.complexity,
        }
    
    # For long responses, generate a brief summary for conversation context
    is_proposal = False
    if think_output and hasattr(think_output, "decision"):
        is_proposal = think_output.decision in ("propose", "clarify")
    
    assistant_summary = await _summarize_assistant_response(final_response, is_proposal)
    
    current_turn = create_conversation_turn(
        user_message=user_message,
        assistant_response=final_response,
        assistant_summary=assistant_summary,
        routing=routing_info,
    )
    
    # ==========================================================================
    # 2. Update conversation history
    # ==========================================================================
    
    # Get recent turns
    recent_turns = list(conversation.get("recent_turns", []))
    recent_turns.append(current_turn)
    
    # Compress older turns if threshold exceeded (LLM call)
    conversation_summary = conversation.get("history_summary", "")
    
    if len(recent_turns) > FULL_DETAIL_TURNS:
        # Compress oldest turns into summary
        turns_to_compress = recent_turns[:-FULL_DETAIL_TURNS]
        recent_turns = recent_turns[-FULL_DETAIL_TURNS:]
    
        # LLM-compress turns into narrative (no entity IDs, just conversation arc)
        conversation_summary = await _compress_turns_to_narrative(
            existing_summary=conversation_summary,
            turns_to_compress=turns_to_compress,
        )
        logger.info(f"Summarize: Compressed {len(turns_to_compress)} turns to narrative")
    
    # V4 CONSOLIDATION: Persist id_registry across turns
    # This is what allows generated content to survive cross-turn references
    # CRITICAL: Serialize to dict for JSON storage in web sessions
    id_registry = state.get("id_registry")
    # Handle both SessionIdRegistry objects and raw dicts (from prior sessions)
    if id_registry is None:
        id_registry_data = None
        logger.warning("Summarize: id_registry is None in state! Entities will be lost.")
    elif isinstance(id_registry, dict):
        # Reconstruct to call cleanup method
        registry_obj = SessionIdRegistry.from_dict(id_registry)
        cleared = registry_obj.clear_turn_promoted_artifacts()
        if cleared > 0:
            logger.info(f"Summarize: Cleared {cleared} promoted artifacts (turn end)")
        id_registry_data = registry_obj.to_dict()
    else:
        # V4.1: Clear promoted artifacts at turn end
        cleared = id_registry.clear_turn_promoted_artifacts()
        if cleared > 0:
            logger.info(f"Summarize: Cleared {cleared} promoted artifacts (turn end)")
        id_registry_data = id_registry.to_dict()
    
    updated_conversation = {
        "recent_turns": recent_turns,
        "history_summary": conversation_summary,
        "engagement_summary": conversation.get("engagement_summary", ""),
        "active_entities": conversation.get("active_entities", {}),
        "all_entities": conversation.get("all_entities", {}),
        "content_archive": conversation.get("content_archive", {}),
        "step_summaries": conversation.get("step_summaries", []),
        "id_registry": id_registry_data,  # V4: Serialized for JSON storage
    }
    
    # ==========================================================================
    # 3. Track pending clarification
    # ==========================================================================
    
    if think_output and hasattr(think_output, "decision"):
        decision = think_output.decision
        if decision in ("propose", "clarify"):
            updated_conversation["pending_clarification"] = {
                "type": decision,
                "goal": getattr(think_output, "goal", ""),
                "questions": getattr(think_output, "clarification_questions", None),
                "proposal_message": getattr(think_output, "proposal_message", None),
            }
        else:
            updated_conversation["pending_clarification"] = None
    
    understand_output = state.get("understand_output")
    if understand_output and hasattr(understand_output, "needs_clarification"):
        if understand_output.needs_clarification:
            updated_conversation["pending_clarification"] = {
                "type": "understand",
                "questions": getattr(understand_output, "clarification_questions", None),
            }
    
    # ==========================================================================
    # 3b. V5: Store Understand's decision log entries
    # ==========================================================================
    
    decision_log = conversation.get("understand_decision_log", [])
    new_entries = state.get("understand_decision_log_entries", [])
    if new_entries:
        decision_log = decision_log + new_entries
        # Keep last 20 entries to prevent unbounded growth
        decision_log = decision_log[-20:]
        logger.info(f"Summarize: Added {len(new_entries)} Understand decision log entries")
    updated_conversation["understand_decision_log"] = decision_log
    
    # ==========================================================================
    # 4. Build SummarizeOutput (structured audit ledger, no LLM)
    # ==========================================================================
    
    summarize_output = _build_summarize_output(
        step_results=step_results,
        step_metadata=state.get("step_metadata", {}),
        think_output=think_output,
    )
    
    # ==========================================================================
    # 4b. V6: Build TurnExecutionSummary (Layer 3 - Reasoning Trace)
    # ==========================================================================
    
    turn_summary = _build_turn_execution_summary(
        turn_num=current_turn_num,  # workflow already incremented
        user_message=user_message,
        think_output=think_output,
        step_results=step_results,
        step_metadata=state.get("step_metadata", {}),
        understand_output=state.get("understand_output"),
    )
    
    # Store in turn_summaries (keep last 2)
    turn_summaries = list(conversation.get("turn_summaries", []))
    turn_summaries.append(turn_summary.model_dump())
    
    # Compress older summaries if beyond threshold
    reasoning_summary = conversation.get("reasoning_summary", "")
    if len(turn_summaries) > 2:
        summaries_to_compress = turn_summaries[:-2]
        turn_summaries = turn_summaries[-2:]
        
        # Compress to reasoning_summary (simple concatenation for now, could be LLM)
        reasoning_summary = _compress_turn_summaries(
            existing_summary=reasoning_summary,
            summaries_to_compress=summaries_to_compress,
        )
        logger.info(f"Summarize: Compressed {len(summaries_to_compress)} turn summaries")
    
    updated_conversation["turn_summaries"] = turn_summaries
    updated_conversation["reasoning_summary"] = reasoning_summary
    
    # ==========================================================================
    # 5. V5: Persist step_results for cross-turn entity data access
    # 
    # This is the key to Act seeing full entity data from prior turns.
    # - Active entities (last 2 turns) get FULL data from turn_step_results
    # - Long-term memory (>2 turns) gets refs only
    # - Token cost: ~20-40 lines per entity vs 300+ lines for re-read calls
    # ==========================================================================
    
    turn_step_results = dict(conversation.get("turn_step_results", {}))
    if step_results:
        # Store this turn's step results keyed by turn number (workflow already incremented)
        turn_step_results[str(current_turn_num)] = _serialize_step_results(step_results)
        
        # Prune to last 2 turns (matches active entity window)
        turn_keys = sorted(turn_step_results.keys(), key=int, reverse=True)
        for old_key in turn_keys[2:]:
            del turn_step_results[old_key]
            logger.info(f"Summarize: Pruned turn_step_results for turn {old_key}")
    
    updated_conversation["turn_step_results"] = turn_step_results
    
    # ==========================================================================
    # 6. V4 CONSOLIDATION: Update turn number only
    # Entity tracking is handled by SessionIdRegistry in Act node
    # ==========================================================================
    
    # Store current turn (workflow already incremented at turn start)
    updated_conversation["current_turn"] = current_turn_num
    
    return {
        "conversation": updated_conversation,
        "summarize_output": summarize_output.model_dump(),
        "current_turn": current_turn_num,
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
    # For proposals/clarifications: KEEP THE FULL TEXT (with reasonable truncation)
    # Think NEEDS to see what was proposed to plan the next step correctly
    if is_proposal:
        # Proposals are usually short - just keep them (truncate at 500 chars if needed)
        if len(response) < 500:
            return response
        else:
            # Truncate but keep the essential proposal text
            return response[:500] + "..."
    
    if len(response) < SUMMARIZE_THRESHOLD:
        return response  # Short enough, keep as-is
    
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


async def _compress_turns_to_narrative(
    existing_summary: str,
    turns_to_compress: list[dict],
) -> str:
    """
    V4: Compress conversation turns into narrative summary.
    
    Focus on conversation arc, NOT entity IDs:
    - What was the user trying to accomplish?
    - What did Alfred do?
    - Any key decisions made?
    
    This is for conversation context, not entity tracking.
    Entity tracking is handled by EntityContextModel.
    """
    if not turns_to_compress:
        return existing_summary
    
    # Format turns for summarization
    turns_text = ""
    for turn in turns_to_compress:
        user_msg = turn.get("user", "")[:200]
        assistant_msg = turn.get("assistant_summary") or turn.get("assistant", "")[:200]
        turns_text += f"User: {user_msg}\nAlfred: {assistant_msg}\n\n"
    
    try:
        result = await call_llm(
            response_model=TurnSummary,
            system_prompt="""Summarize this conversation in 2-3 sentences.
            
Focus on:
- What the user wanted to accomplish
- Key actions taken or decisions made
- Overall conversation arc

Do NOT include:
- Entity IDs or UUIDs
- Technical details
- Step-by-step breakdowns

Write as a narrative: "User explored meal planning options, decided on 3 fish recipes..."
""",
            user_prompt=f"""Existing summary: {existing_summary or 'None'}

New turns to incorporate:
{turns_text}

Write a brief narrative summary:""",
            complexity="low",
        )
        
        # Combine with existing
        if existing_summary:
            return f"{existing_summary} {result.summary}"
        return result.summary
        
    except Exception as e:
        logger.warning(f"Failed to compress turns: {e}")
        # Fallback: just concatenate key points
        if existing_summary:
            return existing_summary
        return "Prior conversation context available."


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


# =============================================================================
# V4: Build Structured Summarize Output
# =============================================================================


def _build_summarize_output(
    step_results: dict[int, Any],
    step_metadata: dict[int, dict],
    think_output: Any,
) -> SummarizeOutput:
    """
    V4 CONSOLIDATION: Build structured SummarizeOutput from turn data.
    
    Produces machine-readable audit ledger, not narrative.
    Entity tracking is now done by SessionIdRegistry - we just count artifacts here.
    """
    output = SummarizeOutput()
    
    # Count steps
    output.steps_total = len(think_output.steps) if think_output else 0
    output.steps_completed = len(step_results)
    
    # Track artifacts generated vs saved
    for step_idx, metadata in step_metadata.items():
        step_type = metadata.get("step_type")
        artifacts = metadata.get("artifacts", [])
        
        if step_type == "generate" and artifacts:
            for artifact in artifacts:
                if isinstance(artifact, dict):
                    artifact_type = _infer_artifact_type(artifact)
                    output.artifacts_generated[artifact_type] = output.artifacts_generated.get(artifact_type, 0) + 1
        
        elif step_type == "write":
            # Check step_results for saved counts
            result = step_results.get(step_idx)
            if result:
                saved_count = _count_saved_in_result(result)
                for artifact_type, count in saved_count.items():
                    output.artifacts_saved[artifact_type] = output.artifacts_saved.get(artifact_type, 0) + count
    
    # Build factual turn summary
    parts = []
    
    if think_output:
        goal = getattr(think_output, "goal", "")
        if goal:
            parts.append(f"Goal: {goal[:50]}")
    
    if output.entities_created:
        parts.append(f"{len(output.entities_created)} created")
    
    if output.artifacts_generated:
        gen_str = ", ".join(f"{count} {t}" for t, count in output.artifacts_generated.items())
        parts.append(f"generated: {gen_str}")
    
    if output.artifacts_saved:
        saved_str = ", ".join(f"{count} {t}" for t, count in output.artifacts_saved.items())
        parts.append(f"saved: {saved_str}")
    
    if output.errors:
        parts.append(f"{len(output.errors)} errors")
    
    output.turn_summary = "; ".join(parts) if parts else "Turn completed"
    
    return output


def _infer_artifact_type(artifact: dict) -> str:
    """Infer artifact type from structure."""
    if "instructions" in artifact or "cuisine" in artifact:
        return "recipe"
    if "meal_type" in artifact and "date" in artifact:
        return "meal_plan"
    if "due_date" in artifact or ("title" in artifact and "status" in artifact):
        return "task"
    return "item"


def _count_saved_in_result(result: Any) -> dict[str, int]:
    """Count saved items by type from a step result."""
    counts: dict[str, int] = {}
    
    if isinstance(result, list):
        for item in result:
            if isinstance(item, tuple) and len(item) >= 3:
                tool, table, data = item[:3]
                if tool == "db_create":
                    item_type = _table_to_type(table)
                    count = len(data) if isinstance(data, list) else 1
                    counts[item_type] = counts.get(item_type, 0) + count
    
    return counts


def _table_to_type(table: str) -> str:
    """Convert table name to entity type."""
    mapping = {
        "recipes": "recipe",
        "recipe_ingredients": "ingredient",
        "meal_plans": "meal_plan",
        "tasks": "task",
        "inventory": "inventory",
        "shopping_list": "shopping",
    }
    return mapping.get(table, table)


# =============================================================================
# V4: Query Pattern Extraction
# =============================================================================


def _extract_successful_query_patterns(
    step_results: dict[int, Any],
    step_metadata: dict[int, dict],
) -> list[dict]:
    """
    Extract successful query patterns from read steps.
    
    When a read step returns results, we save the query pattern
    so future turns can reference what worked.
    
    Returns list of patterns: [{subdomain, filters, record_count}]
    """
    patterns = []
    
    for step_idx, meta in step_metadata.items():
        step_type = meta.get("step_type")
        if step_type != "read":
            continue
        
        result = step_results.get(step_idx)
        if not result:
            continue
        
        # Check if this read returned data
        record_count = _count_records(result)
        if record_count == 0:
            continue
        
        # Extract the query pattern
        subdomain = meta.get("subdomain", "")
        description = meta.get("description", "")
        
        # Try to infer filters from description
        filters = []
        desc_lower = description.lower()
        
        # Common filter patterns in descriptions
        if "expir" in desc_lower:
            filters.append("expiry_date")
        if "vegetarian" in desc_lower or "vegan" in desc_lower:
            filters.append("dietary")
        if any(cuisine in desc_lower for cuisine in ["italian", "mexican", "asian", "indian"]):
            filters.append("cuisine")
        if "quick" in desc_lower or "under 30" in desc_lower:
            filters.append("time")
        
        pattern = {
            "subdomain": subdomain,
            "description_hint": description[:50],
            "filters_inferred": filters,
            "record_count": record_count,
            "step_idx": step_idx,
        }
        patterns.append(pattern)
    
    return patterns


# =============================================================================
# V6: Turn Execution Summary Builder (Layer 3 - Reasoning Trace)
# =============================================================================


def _build_turn_execution_summary(
    turn_num: int,
    user_message: str,
    think_output: Any,
    step_results: dict[int, Any],
    step_metadata: dict[int, dict],
    understand_output: Any,
) -> TurnExecutionSummary:
    """
    Build TurnExecutionSummary from turn data.
    
    This is the core of Layer 3 (Reasoning Trace).
    Captures what happened and why, for Think/Reply context in next turn.
    """
    summary = TurnExecutionSummary(turn_num=turn_num)
    
    # Extract Think's decision
    if think_output:
        summary.think_decision = getattr(think_output, "decision", "")
        summary.think_goal = getattr(think_output, "goal", "")
    
    # Build step summaries
    steps = think_output.steps if think_output else []
    for idx, result in step_results.items():
        step_meta = step_metadata.get(idx, {})
        step_desc = steps[idx].description if idx < len(steps) else f"Step {idx + 1}"
        step_type = step_meta.get("step_type") or (steps[idx].step_type if idx < len(steps) else "read")
        subdomain = step_meta.get("subdomain") or (steps[idx].subdomain if idx < len(steps) else "")
        
        # Build outcome from result
        outcome = _summarize_step_result(result)
        
        # Extract entities involved
        entities = _extract_entity_ids(result)
        
        # Get note from metadata (if stored)
        note = step_meta.get("note_for_next_step")
        
        summary.steps.append(StepExecutionSummary(
            step_num=idx,
            step_type=step_type,
            subdomain=subdomain,
            description=step_desc,
            outcome=outcome,
            entities_involved=entities,
            note=note,
        ))
    
    # Extract Understand's curation
    if understand_output and hasattr(understand_output, "entity_curation"):
        curation = understand_output.entity_curation
        if curation:
            summary.entity_curation = CurationSummary(
                retained=[r.ref for r in getattr(curation, "retain_active", [])],
                demoted=getattr(curation, "demote", []),
                reasons={r.ref: r.reason for r in getattr(curation, "retain_active", [])},
            )
    
    # Infer conversation phase
    summary.conversation_phase = _infer_conversation_phase(think_output, step_results)
    
    # Extract user expression (simple heuristic)
    summary.user_expressed = _extract_user_expression(user_message)
    
    return summary


def _infer_conversation_phase(think_output: Any, step_results: dict) -> str:
    """
    Infer conversation phase from Think decision and step types.
    
    Phases:
    - exploring: Reading, browsing, clarifying
    - narrowing: Analyzing, filtering, comparing
    - confirming: Proposing, generating drafts
    - executing: Writing, saving
    """
    if not think_output:
        return "exploring"
    
    decision = getattr(think_output, "decision", "")
    
    # Proposals and clarifications are exploring/confirming
    if decision in ("propose", "clarify"):
        return "exploring"
    
    # Check step types
    if not step_results:
        return "exploring"
    
    steps = think_output.steps if hasattr(think_output, "steps") else []
    step_types = [getattr(s, "step_type", "read") for s in steps]
    
    if "write" in step_types:
        return "executing"
    if "generate" in step_types:
        return "confirming"
    if "analyze" in step_types:
        return "narrowing"
    
    return "exploring"


def _extract_user_expression(user_message: str) -> str:
    """
    Extract what user expressed (simple heuristic).
    
    This is a lightweight extraction - could be enhanced with LLM.
    """
    msg_lower = user_message.lower()
    
    # Exclusion patterns
    if "no " in msg_lower or "not " in msg_lower or "exclude" in msg_lower:
        # Try to extract what they're excluding
        for pattern in ["no ", "not ", "exclude "]:
            if pattern in msg_lower:
                idx = msg_lower.find(pattern)
                rest = user_message[idx:idx + 50].split()[1:3]  # Next 1-2 words
                if rest:
                    return f"excluded: {' '.join(rest)}"
    
    # Preference patterns
    if "want" in msg_lower or "prefer" in msg_lower:
        return "expressed preference"
    
    if "quick" in msg_lower or "fast" in msg_lower:
        return "wants quick options"
    
    if "?" in user_message:
        return "asked question"
    
    # Confirmation patterns
    if any(word in msg_lower for word in ["yes", "ok", "sure", "sounds good", "perfect"]):
        return "confirmed"
    
    return ""


def _serialize_step_results(step_results: dict[int, Any]) -> dict[str, Any]:
    """
    Serialize step_results for JSON storage in conversation.
    
    Converts integer keys to strings (JSON requires string keys).
    Extracts actual data from tool result tuples for cleaner storage.
    
    Storage format per step:
    {
        "0": {
            "data": [...records...],
            "table": "recipes",
            "tool": "db_read"
        }
    }
    """
    serialized = {}
    
    for step_idx, result in step_results.items():
        step_key = str(step_idx)
        
        # Handle tool result tuples: (tool, table, data) or (tool, data)
        if isinstance(result, list) and result and isinstance(result[0], tuple):
            # Multiple tool calls in this step - take the last one's data
            last_call = result[-1]
            if len(last_call) == 3:
                tool, table, data = last_call
                serialized[step_key] = {
                    "data": data,
                    "table": table,
                    "tool": tool,
                }
            elif len(last_call) == 2:
                tool, data = last_call
                serialized[step_key] = {
                    "data": data,
                    "tool": tool,
                }
            else:
                serialized[step_key] = {"data": result}
        else:
            # Raw data (analyze/generate results)
            serialized[step_key] = {"data": result}
    
    return serialized


def _compress_turn_summaries(
    existing_summary: str,
    summaries_to_compress: list[dict],
) -> str:
    """
    Compress older turn summaries into reasoning_summary.
    
    Simple concatenation for now - could be LLM-enhanced later.
    """
    compressed_parts = []
    
    for ts in summaries_to_compress:
        turn_num = ts.get("turn_num", "?")
        goal = ts.get("think_goal", "")
        phase = ts.get("conversation_phase", "")
        
        if goal:
            compressed_parts.append(f"Turn {turn_num}: {goal}")
        elif phase:
            compressed_parts.append(f"Turn {turn_num}: {phase}")
    
    new_summary = "; ".join(compressed_parts)
    
    if existing_summary:
        return f"{existing_summary}; {new_summary}"
    
    return new_summary
