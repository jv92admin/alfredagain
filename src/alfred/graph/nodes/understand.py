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


def _format_recent_turns(turns: list[dict], limit: int = 2) -> str:
    """Format recent conversation turns."""
    if not turns:
        return "No previous turns."
    
    recent = turns[-limit:]
    lines = []
    for turn in recent:
        user_msg = turn.get("user", "")[:200]  # Truncate
        assistant_msg = turn.get("assistant_summary") or turn.get("assistant", "")[:200]
        lines.append(f"User: {user_msg}")
        lines.append(f"Alfred: {assistant_msg}")
        lines.append("")
    
    return "\n".join(lines)


def _format_active_entities_from_conversation(active: dict[str, dict]) -> str:
    """Format active_entities from conversation context (same source as Think)."""
    if not active:
        return "None"
    
    lines = []
    for entity_id, entity_data in list(active.items())[:20]:  # Limit to 20
        etype = entity_data.get("type", "unknown")
        label = entity_data.get("label", "unknown")
        # V4: IDs are simple refs, show in full
        lines.append(f"- {etype}: {label} ({entity_id})")
    
    if len(active) > 20:
        lines.append(f"... and {len(active) - 20} more")
    
    return "\n".join(lines)


def _build_understand_context(state: AlfredState) -> str:
    """
    Build context for Understand prompt.
    
    V4 CONSOLIDATION: Uses SessionIdRegistry for all entity display.
    """
    parts = []
    
    # User message
    parts.append(f"## User Message\n\n{state['user_message']}")
    
    # V4 CONSOLIDATION: Load SessionIdRegistry and format for Understand
    registry_data = state.get("id_registry")
    if registry_data:
        registry = SessionIdRegistry.from_dict(registry_data)
        parts.append(registry.format_for_understand_prompt())
    else:
        parts.append("## Entity Registry\n\n*No entities tracked yet.*")
    
    # Recent turns
    conversation = state.get("conversation", {})
    recent_turns = conversation.get("recent_turns", [])
    parts.append(f"## Recent Conversation\n\n{_format_recent_turns(recent_turns)}")
    
    # Pending clarification context
    pending_clarification = conversation.get("pending_clarification")
    if pending_clarification:
        parts.append(f"## Pending Clarification\n\nPreviously asked: {pending_clarification}")
    
    return "\n\n".join(parts)




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
                "understand_output": UnderstandOutput(
                    processed_message=state["user_message"]
                )
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
                "You are Alfred's lightweight pre-processor. "
                "Your job: (1) resolve references to IDs from Recent Items, "
                "(2) detect quick mode for simple READ-ONLY queries (never for writes/deletes/multi-step), "
                "(3) write a simple processed_message. "
                "NEVER invent entity IDs. Keep processed_message short — Think does the planning."
            ),
            user_prompt=full_prompt,
            complexity="medium",  # Upgraded from low - context inference needs smarter model
        )
    except Exception as e:
        logger.warning(f"Failed to parse Understand response: {e}")
        output = UnderstandOutput(
            processed_message=state["user_message"]
        )
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
            # Rewrite output to NOT clarify
            output = UnderstandOutput(
                processed_message=f"User answered clarification: {state['user_message']}",
                entity_updates=output.entity_updates,
                referenced_entities=output.referenced_entities,
                needs_clarification=False,
                clarification_questions=None,
                clarification_reason=None,
            )
    
    # V4 CONSOLIDATION: Touch referenced entities in SessionIdRegistry
    current_turn = state.get("current_turn", 0)
    registry_data = state.get("id_registry")
    registry = SessionIdRegistry.from_dict(registry_data) if registry_data else SessionIdRegistry(session_id=state.get("conversation_id", ""))
    registry.set_turn(current_turn)
    
    # Touch referenced entities (updates last_ref time)
    for entity_id in output.referenced_entities:
        registry.touch_ref(entity_id)
        logger.debug(f"Understand: Touched {entity_id}")
    
    # V4 CONSOLIDATION: Entity curation is now just dropping refs from registry
    # No more promote/demote - we just track recency via touch_ref
    if output.entity_curation:
        curation = output.entity_curation
        
        if curation.clear_all:
            # Clear all refs (fresh start)
            for ref in list(registry.ref_to_uuid.keys()):
                registry.remove_ref(ref)
            logger.info("Understand: Cleared all entities (user requested fresh start)")
        elif curation.drop_entities:
            for ref in curation.drop_entities:
                registry.remove_ref(ref)
            logger.info(f"Understand: Dropped {len(curation.drop_entities)} entities")
    
    return {
        "understand_output": output,
        "id_registry": registry.to_dict(),  # V4 CONSOLIDATION: Single source of truth
    }

