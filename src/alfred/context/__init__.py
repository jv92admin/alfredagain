"""
Alfred Context API - Unified context building for all nodes.

Three-Layer Context Model:
- Layer 1: Entity Context (what objects exist)
- Layer 2: Conversation History (what was said)
- Layer 3: Reasoning Trace (what LLMs decided)

Each node subscribes to specific slices via build_*_context() functions.
"""

from alfred.context.entity import (
    EntityContext,
    EntitySnapshot,
    get_entity_context,
    format_entity_context,
)
from alfred.context.conversation import (
    ConversationHistory,
    PendingState,
    get_conversation_history,
    format_conversation,
)
from alfred.context.reasoning import (
    ReasoningTrace,
    TurnSummary,
    StepSummary,
    CurationSummary,
    get_reasoning_trace,
    format_reasoning,
)
from alfred.context.builders import (
    build_understand_context,
    build_think_context,
    build_act_context,
    build_reply_context,
)

__all__ = [
    # Entity Layer
    "EntityContext",
    "EntitySnapshot",
    "get_entity_context",
    "format_entity_context",
    # Conversation Layer
    "ConversationHistory",
    "PendingState",
    "get_conversation_history",
    "format_conversation",
    # Reasoning Layer
    "ReasoningTrace",
    "TurnSummary",
    "StepSummary",
    "CurationSummary",
    "get_reasoning_trace",
    "format_reasoning",
    # Node Builders
    "build_understand_context",
    "build_think_context",
    "build_act_context",
    "build_reply_context",
]
