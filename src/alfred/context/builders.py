"""
Alfred Context API - Node-Specific Context Builders.

Each node gets a tailored context builder that assembles
the right slices from each of the three layers.

Usage:
    ctx = build_think_context(state)
    prompt_section = ctx.format()
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from alfred.context.entity import (
    EntityContext,
    get_entity_context,
    format_entity_context,
)
from alfred.context.conversation import (
    ConversationHistory,
    get_conversation_history,
    format_conversation,
    format_conversation_brief,
)
from alfred.context.reasoning import (
    ReasoningTrace,
    CurationSummary,
    get_reasoning_trace,
    get_current_turn_curation,
    format_reasoning,
    format_curation_for_think,
)

if TYPE_CHECKING:
    from alfred.graph.state import AlfredState


# =============================================================================
# Context Containers (What Each Node Receives)
# =============================================================================


@dataclass
class UnderstandContext:
    """Context for Understand's curation decisions."""
    
    entity: EntityContext
    conversation: ConversationHistory
    decision_history: list[dict]  # Own decision log
    
    def format(self) -> str:
        """Format full context for Understand prompt."""
        sections = []
        
        # Full entity context for curation decisions
        entity_section = format_entity_context(self.entity, mode="full")
        if entity_section:
            sections.append(f"## Entity Context\n\n{entity_section}")
        
        # Full conversation for intent understanding
        conv_section = format_conversation(self.conversation, depth=3)
        if conv_section:
            sections.append(f"## Conversation History\n\n{conv_section}")
        
        # Own decision history for continuity
        if self.decision_history:
            history_lines = []
            for entry in self.decision_history[-5:]:  # Last 5 decisions
                action = entry.get("action", "")
                ref = entry.get("ref", "")
                reason = entry.get("reason", "")
                history_lines.append(f"- {action} `{ref}`: {reason}")
            if history_lines:
                sections.append(f"## Your Previous Decisions\n\n{chr(10).join(history_lines)}")
        
        return "\n\n".join(sections)


@dataclass
class ThinkContext:
    """Context for Think's planning decisions."""
    
    entity: EntityContext
    conversation: ConversationHistory
    reasoning: ReasoningTrace
    curation: CurationSummary | None  # Current turn's Understand decisions
    
    def format(self) -> str:
        """Format full context for Think prompt."""
        sections = []
        
        # Entity context (refs + labels, with "do not re-read" framing)
        entity_section = format_entity_context(self.entity, mode="do_not_read")
        if entity_section and "No entities" not in entity_section:
            sections.append(f"## Entity Context\n\n{entity_section}")
        
        # Conversation history (full + pending)
        conv_section = format_conversation(self.conversation, depth=2, include_pending=True)
        if conv_section:
            sections.append(f"## Conversation History\n\n{conv_section}")
        
        # Reasoning trace (what happened last turn)
        reasoning_section = format_reasoning(self.reasoning, node="think")
        if reasoning_section and "No prior" not in reasoning_section:
            sections.append(f"## What Happened Last Turn\n\n{reasoning_section}")
        
        # Current turn's curation (from Understand)
        curation_section = format_curation_for_think(self.curation)
        if curation_section:
            sections.append(curation_section)
        
        return "\n\n".join(sections)


@dataclass
class ActContext:
    """Context for Act's execution."""
    
    entity: EntityContext
    conversation: ConversationHistory
    current_step_results: dict  # Results from steps so far this turn
    prev_step_note: str | None  # Note from previous step
    
    def format(self) -> str:
        """Format context for Act prompt."""
        sections = []
        
        # Full entity data for execution
        entity_section = format_entity_context(self.entity, mode="full")
        if entity_section:
            sections.append(f"## Entity Context\n\n{entity_section}")
        
        # Brief conversation (just last exchange)
        conv_section = format_conversation_brief(self.conversation)
        if conv_section:
            sections.append(f"## Conversation\n\n{conv_section}")
        
        # Previous step note
        if self.prev_step_note:
            sections.append(f"## Previous Step Note\n\n{self.prev_step_note}")
        
        return "\n\n".join(sections)


@dataclass
class ReplyContext:
    """Context for Reply's response generation."""
    
    entity: EntityContext
    conversation: ConversationHistory
    reasoning: ReasoningTrace
    execution_outcome: str  # What was accomplished
    
    def format(self) -> str:
        """Format context for Reply prompt."""
        sections = []
        
        # Labels only for natural language
        entity_section = format_entity_context(self.entity, mode="labels_only")
        if entity_section and "No entities" not in entity_section:
            sections.append(f"## Available Entities\n\n{entity_section}")
        
        # Conversation with engagement summary
        conv_section = format_conversation(self.conversation, depth=2)
        if conv_section:
            sections.append(f"## Conversation\n\n{conv_section}")
        
        # Reasoning for continuity (phase, user expressed)
        reasoning_section = format_reasoning(self.reasoning, node="reply")
        if reasoning_section and "No prior" not in reasoning_section:
            sections.append(f"## Conversation Flow\n\n{reasoning_section}")
        
        # What was accomplished
        if self.execution_outcome:
            sections.append(f"## What Was Accomplished\n\n{self.execution_outcome}")
        
        return "\n\n".join(sections)


# =============================================================================
# Builder Functions (Entry Points)
# =============================================================================


def build_understand_context(state: "AlfredState") -> UnderstandContext:
    """
    Build context for Understand's curation decisions.
    
    Includes:
    - Full entity context (all tiers)
    - Full conversation history + pending
    - Own decision history for continuity
    """
    conversation = state.get("conversation", {})
    registry = state.get("id_registry", {})
    current_turn = state.get("current_turn", 0)
    
    return UnderstandContext(
        entity=get_entity_context(registry, current_turn, mode="curation"),
        conversation=get_conversation_history(conversation),
        decision_history=conversation.get("understand_decision_log", []),
    )


def build_think_context(state: "AlfredState") -> ThinkContext:
    """
    Build context for Think's planning decisions.
    
    Includes:
    - Entity refs + labels (not full data)
    - Full conversation + pending
    - Last turn summary + curation
    - Current turn's Understand decisions
    """
    conversation = state.get("conversation", {})
    registry = state.get("id_registry", {})
    current_turn = state.get("current_turn", 0)
    
    return ThinkContext(
        entity=get_entity_context(registry, current_turn, mode="refs_and_labels"),
        conversation=get_conversation_history(conversation),
        reasoning=get_reasoning_trace(conversation),
        curation=get_current_turn_curation(state),
    )


def build_act_context(state: "AlfredState") -> ActContext:
    """
    Build context for Act's execution.
    
    Includes:
    - Full entity data (active + generated)
    - Brief conversation (last exchange)
    - Current turn step results
    - Previous step note
    """
    conversation = state.get("conversation", {})
    registry = state.get("id_registry", {})
    current_turn = state.get("current_turn", 0)
    
    return ActContext(
        entity=get_entity_context(registry, current_turn, mode="full"),
        conversation=get_conversation_history(conversation),
        current_step_results=state.get("step_results", {}),
        prev_step_note=state.get("prev_step_note"),
    )


def build_reply_context(state: "AlfredState") -> ReplyContext:
    """
    Build context for Reply's response generation.
    
    Includes:
    - Entity labels only (for natural language)
    - Conversation with engagement summary
    - Reasoning trace (phase, user expressed)
    - Execution outcome summary
    """
    conversation = state.get("conversation", {})
    registry = state.get("id_registry", {})
    current_turn = state.get("current_turn", 0)
    
    # Build execution outcome from step_results
    step_results = state.get("step_results", {})
    think_output = state.get("think_output")
    outcome = _build_execution_outcome(step_results, think_output)
    
    return ReplyContext(
        entity=get_entity_context(registry, current_turn, mode="labels_only"),
        conversation=get_conversation_history(conversation),
        reasoning=get_reasoning_trace(conversation),
        execution_outcome=outcome,
    )


def _build_execution_outcome(step_results: dict, think_output) -> str:
    """Build a brief execution outcome summary for Reply."""
    if not step_results:
        return ""
    
    outcomes = []
    steps = think_output.steps if think_output else []
    
    for idx, result in step_results.items():
        step_desc = steps[idx].description if idx < len(steps) else f"Step {idx + 1}"
        
        # Count results
        if isinstance(result, list):
            if result and isinstance(result[0], tuple):
                # Tool result format: [(tool, table, data), ...]
                total = sum(len(r[-1]) if isinstance(r[-1], list) else 1 for r in result)
                outcomes.append(f"{step_desc}: {total} items")
            else:
                outcomes.append(f"{step_desc}: {len(result)} items")
        elif isinstance(result, dict):
            outcomes.append(f"{step_desc}: completed")
        else:
            outcomes.append(f"{step_desc}: done")
    
    return "; ".join(outcomes)
