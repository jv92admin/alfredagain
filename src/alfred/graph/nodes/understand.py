"""
Alfred V3 - Understand Node.

The Understand node handles:
1. Entity state updates (confirmation/rejection signals)
2. Entity reference resolution ("that recipe" → specific ID)
3. Clarification detection

Understand does NOT plan steps. That's Think's job.
"""

import logging
from pathlib import Path
from typing import Any

from alfred.core.modes import Mode, ModeContext
from alfred.core.id_registry import SessionIdRegistry
from alfred.graph.state import AlfredState, UnderstandOutput
from alfred.llm.client import call_llm, set_current_node

logger = logging.getLogger(__name__)

# Load prompt template
PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "understand.md"


def _load_prompt() -> str:
    """Load the understand prompt template."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    else:
        logger.warning(f"Understand prompt not found at {PROMPT_PATH}")
        return "Analyze the user message and detect entity state changes."


def _format_conversation_with_entities(
    turns: list[dict], 
    registry: SessionIdRegistry | None,
    current_turn_num: int,
    limit: int = 5
) -> str:
    """
    V5: Format conversation history with entity annotations.
    
    Shows last N turns with what entities were involved in each.
    This helps Understand see the connection between conversation and entities.
    """
    if not turns:
        return "*No previous conversation.*"
    
    recent = turns[-limit:]
    lines = []
    
    # Calculate turn numbers (working backwards from current)
    start_turn = max(1, current_turn_num - len(recent))
    
    for i, turn in enumerate(recent):
        turn_num = start_turn + i
        turns_ago = current_turn_num - turn_num
        ago_label = f"({turns_ago} turn{'s' if turns_ago != 1 else ''} ago)" if turns_ago > 0 else "(current)"
        
        lines.append(f"### Turn {turn_num} {ago_label}")
        
        user_msg = turn.get("user", "")
        if len(user_msg) > 300:
            user_msg = user_msg[:300] + "..."
        lines.append(f"**User:** {user_msg}")
        
        assistant_msg = turn.get("assistant_summary") or turn.get("assistant", "")
        if len(assistant_msg) > 300:
            assistant_msg = assistant_msg[:300] + "..."
        lines.append(f"**Alfred:** {assistant_msg}")
        
        # Show entities mentioned/affected this turn (from registry temporal data)
        if registry:
            turn_entities = []
            for ref in registry.ref_to_uuid.keys():
                created_turn = registry.ref_turn_created.get(ref, 0)
                last_ref_turn = registry.ref_turn_last_ref.get(ref, 0)
                action = registry.ref_actions.get(ref, "")
                label = registry.ref_labels.get(ref, ref)
                
                # Entity was created or last referenced this turn
                if created_turn == turn_num:
                    turn_entities.append(f"`{ref}`: {label} ({action})")
                elif last_ref_turn == turn_num and created_turn != turn_num:
                    turn_entities.append(f"`{ref}`: {label} (referenced)")
            
            if turn_entities:
                lines.append(f"**Entities:** {', '.join(turn_entities)}")
        
        lines.append("")
    
    return "\n".join(lines)


def _format_decision_log(decision_log: list[dict], limit: int = 10) -> str:
    """
    V5: Format previous Understand decisions for continuity.
    
    Shows why entities were retained/demoted/dropped in previous turns.
    """
    if not decision_log:
        return "*No previous context decisions.*"
    
    recent = decision_log[-limit:]
    lines = ["| Turn | Entity | Decision | Reason |", "|------|--------|----------|--------|"]
    
    for entry in recent:
        turn = entry.get("turn", "?")
        ref = entry.get("ref", "-")
        action = entry.get("action", "-")
        reason = entry.get("reason", "-")
        if reason and len(reason) > 50:
            reason = reason[:50] + "..."
        lines.append(f"| T{turn} | `{ref}` | {action} | {reason} |")
    
    return "\n".join(lines)


def _build_understand_context(state: AlfredState) -> str:
    """
    V5: Build context for Understand prompt.
    
    Structure:
    1. Current message (prominent)
    2. Conversation history with entity annotations
    3. Previous Understand decisions (continuity)
    4. Entity Registry (reference material)
    """
    parts = []
    conversation = state.get("conversation", {})
    current_turn = state.get("current_turn", 1)
    
    # 1. Current message (prominent, first)
    parts.append(f"## Current Message\n\n\"{state['user_message']}\"")
    
    # Load registry for entity annotations
    registry_data = state.get("id_registry")
    registry = None
    if registry_data:
        if isinstance(registry_data, SessionIdRegistry):
            registry = registry_data
        else:
            registry = SessionIdRegistry.from_dict(registry_data)
    
    # 2. Conversation history with entity annotations (last 4-5 turns)
    recent_turns = conversation.get("recent_turns", [])
    conv_section = _format_conversation_with_entities(recent_turns, registry, current_turn, limit=5)
    parts.append(f"## Recent Conversation\n\n{conv_section}")
    
    # 3. Previous Understand decisions (continuity)
    decision_log = conversation.get("understand_decision_log", [])
    if decision_log:
        log_section = _format_decision_log(decision_log)
        parts.append(f"## Your Previous Decisions\n\nMaintain continuity with past context curation:\n\n{log_section}")
    
    # 4. Entity Registry (reference material)
    if registry:
        parts.append(registry.format_for_understand_prompt())
    else:
        parts.append("## Entity Registry\n\n*No entities tracked yet.*")
    
    # 5. Pending clarification context (if any)
    pending_clarification = conversation.get("pending_clarification")
    if pending_clarification:
        parts.append(f"## Pending Clarification\n\nYou previously asked: {pending_clarification}")
    
    return "\n\n---\n\n".join(parts)




async def understand_node(state: AlfredState) -> dict[str, Any]:
    """
    Understand node: detect signals and update entity states.
    
    This node:
    1. Analyzes the user message for confirmation/rejection signals
    2. Updates entity states (pending → active, etc.)
    3. Resolves entity references
    4. Flags if clarification is needed
    
    Returns state updates including:
    - understand_output: The structured output
    - entity_registry: Updated with state changes
    """
    logger.info("Understand: Processing user message")
    
    # Check if we should skip Understand (Quick mode with simple request)
    mode_data = state.get("mode_context", {})
    if mode_data:
        mode_context = ModeContext.from_dict(mode_data)
        if mode_context.skip_think:
            # Quick mode - minimal understand
            logger.info("Understand: Quick mode, minimal processing")
            return {
                "understand_output": UnderstandOutput()
            }
    
    # Set node name for prompt logging
    set_current_node("understand")
    
    # Build prompt
    base_prompt = _load_prompt()
    context = _build_understand_context(state)
    full_prompt = f"{base_prompt}\n\n---\n\n# Current Request\n\n{context}"
    
    # Check for pending clarification - if user is answering, bias toward proceeding
    conversation = state.get("conversation", {})
    pending_clarification = conversation.get("pending_clarification")
    has_pending = pending_clarification is not None
    
    # Use medium complexity for better context inference
    # (gpt-4.1-mini struggles with "these ingredients" = shopping list just shown)
    try:
        output = await call_llm(
            response_model=UnderstandOutput,
            system_prompt=(
                "You are Alfred's MEMORY MANAGER. "
                "Your job: (1) resolve entity references to simple refs from the registry, "
                "(2) curate context (decide what older entities stay active with reasons), "
                "(3) detect quick mode for simple READ-ONLY queries. "
                "NEVER invent entity refs. Think has the raw message — you just resolve refs and curate context."
            ),
            user_prompt=full_prompt,
            complexity="medium",  # Upgraded from low - context inference needs smarter model
        )
    except Exception as e:
        logger.warning(f"Failed to parse Understand response: {e}")
        output = UnderstandOutput()  # V5: No processed_message needed
    logger.info(f"Understand: entity_updates={len(output.entity_updates)}, "
                f"needs_clarification={output.needs_clarification}")
    
    # Code guard: If user was answering a pending clarification, don't re-clarify
    # This is a safety net for when the LLM is too cautious
    if has_pending and output.needs_clarification:
        user_msg = state["user_message"].lower().strip()
        # If user message references what we asked about, they're answering
        pending_type = pending_clarification.get("type", "")
        # Heuristics for "user is answering":
        # 1. Short response (likely an answer, not new request)
        # 2. Contains reference words (the, those, these, from, my, yes, sure)
        answer_signals = ["the ", "those", "these", "from my", "my ", "yes", "sure", "ok", "yeah"]
        is_short = len(user_msg.split()) < 15
        has_answer_signal = any(sig in user_msg for sig in answer_signals)
        
        if is_short and has_answer_signal:
            logger.info(f"Understand: Overriding re-clarification - user appears to be answering")
            # Rewrite output to NOT clarify (V5: no processed_message)
            output = UnderstandOutput(
                entity_updates=output.entity_updates,
                referenced_entities=output.referenced_entities,
                needs_clarification=False,
                clarification_questions=None,
                clarification_reason=None,
            )
    
    # V4 CONSOLIDATION: Touch referenced entities in SessionIdRegistry
    current_turn = state.get("current_turn", 0)
    registry_data = state.get("id_registry")
    if registry_data is None:
        registry = SessionIdRegistry(session_id=state.get("conversation_id", ""))
    elif isinstance(registry_data, SessionIdRegistry):
        registry = registry_data
    else:
        registry = SessionIdRegistry.from_dict(registry_data)
    registry.set_turn(current_turn)
    
    # Touch referenced entities (updates last_ref time)
    for entity_id in output.referenced_entities:
        registry.touch_ref(entity_id)
        logger.debug(f"Understand: Touched {entity_id}")
    
    # V5: Entity curation with retention reasons
    decision_log_entries = []
    if output.entity_curation:
        curation = output.entity_curation
        
        if curation.clear_all:
            # Clear all refs (fresh start)
            for ref in list(registry.ref_to_uuid.keys()):
                registry.remove_ref(ref)
            logger.info("Understand: Cleared all entities (user requested fresh start)")
            decision_log_entries.append({
                "turn": current_turn,
                "action": "clear_all",
                "reason": curation.curation_summary or "User requested fresh start"
            })
        else:
            # V5: Handle retention decisions (older entities to keep active)
            for retention in curation.retain_active:
                registry.set_active_reason(retention.ref, retention.reason)
                decision_log_entries.append({
                    "turn": current_turn,
                    "ref": retention.ref,
                    "action": "retain",
                    "reason": retention.reason
                })
            
            # Handle demotions (remove active reason)
            for ref in curation.demote:
                registry.clear_active_reason(ref)
                decision_log_entries.append({
                    "turn": current_turn,
                    "ref": ref,
                    "action": "demote",
                    "reason": curation.curation_summary
                })
            
            # Handle drops (remove from registry entirely)
            for ref in curation.drop:
                registry.remove_ref(ref)
                decision_log_entries.append({
                    "turn": current_turn,
                    "ref": ref,
                    "action": "drop",
                    "reason": curation.curation_summary
                })
            
            if curation.retain_active:
                logger.info(f"Understand: Retained {len(curation.retain_active)} entities with reasons")
            if curation.demote:
                logger.info(f"Understand: Demoted {len(curation.demote)} entities")
            if curation.drop:
                logger.info(f"Understand: Dropped {len(curation.drop)} entities")
    
    return {
        "understand_output": output,
        "id_registry": registry.to_dict(),  # V5: Single source of truth
        "understand_decision_log_entries": decision_log_entries,  # V5: For conversation storage
    }

