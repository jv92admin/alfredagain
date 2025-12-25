"""
Alfred V2 - Long-term Memory.

- Embedding storage for semantic search
- Conversation memory for multi-turn recall
- Vector similarity retrieval
"""

from alfred.memory.conversation import (
    add_turn_to_context,
    create_conversation_turn,
    estimate_tokens,
    extract_entities_from_result,
    extract_entities_from_step_results,
    format_condensed_context,
    format_full_context,
    format_step_results_for_context,
    get_entity_data,
    get_step_data,
    initialize_conversation,
    update_active_entities,
)

__all__ = [
    "add_turn_to_context",
    "create_conversation_turn",
    "estimate_tokens",
    "extract_entities_from_result",
    "extract_entities_from_step_results",
    "format_condensed_context",
    "format_full_context",
    "format_step_results_for_context",
    "get_entity_data",
    "get_step_data",
    "initialize_conversation",
    "update_active_entities",
]
