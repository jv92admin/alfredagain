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
from alfred.domain import get_current_domain
from alfred.graph.state import AlfredState, UnderstandOutput
from alfred.context.builders import build_understand_context
from alfred.llm.client import call_llm, set_current_node

logger = logging.getLogger(__name__)

# Load prompt template
PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "templates" / "understand.md"


def _load_prompt() -> str:
    """Load the understand prompt template."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    else:
        logger.warning(f"Understand prompt not found at {PROMPT_PATH}")
        return "Analyze the user message and detect entity state changes."




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
    
    # Build prompt using Context API
    # Domain provides the full prompt body; fall back to core template
    domain = get_current_domain()
    domain_content = domain.get_understand_prompt_content()
    base_prompt = domain_content if domain_content else _load_prompt()
    context = build_understand_context(state).format()
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

