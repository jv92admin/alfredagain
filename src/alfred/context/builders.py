"""
Alfred Context API - Node-Specific Context Builders.

Each node gets a tailored context builder that assembles
the right slices from each of the three layers.

Usage:
    ctx = build_think_context(state)
    prompt_section = ctx.format()

Unified naming convention for all nodes:
- build_understand_context() → UnderstandContext (this module)
- build_think_context() → ThinkContext (this module)
- build_act_entity_context() → str (act.py - requires SessionIdRegistry methods)
- build_reply_context() → ReplyContext (this module)

Note: Act's builder lives in act.py because it requires SessionIdRegistry methods
and complex step_results parsing for full-data injection. The function follows
the unified naming convention: build_act_entity_context().
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from alfred.context.entity import (
    EntityContext,
    get_entity_context,
    format_entity_context,
)
from alfred.context.conversation import (
    ConversationHistory,
    get_conversation_history,
    format_conversation,
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
    from alfred.core.id_registry import SessionIdRegistry


# =============================================================================
# Context Containers (What Each Node Receives)
# =============================================================================


@dataclass
class UnderstandContext:
    """Context for Understand's curation decisions.

    Combines:
    - Entity registry with tabular turn tracking
    - Conversation history with entity annotations
    - Decision history for curation continuity
    """

    user_message: str
    current_turn: int
    recent_turns: list[dict]
    decision_history: list[dict]
    pending_clarification: dict | None
    # Registry data for entity formatting
    registry_data: dict = field(default_factory=dict)

    def format(self) -> str:
        """Format full context for Understand prompt.

        Structure matches understand.py's proven format:
        1. Current message (prominent)
        2. Recent conversation with entity annotations
        3. Previous Understand decisions (table)
        4. Entity Registry with turn tracking (table)
        5. Pending clarification (if any)
        """
        parts = []

        # 1. Current message (prominent, first)
        parts.append(f'## Current Message\n\n"{self.user_message}"')

        # 2. Conversation history with entity annotations
        conv_section = self._format_conversation_with_entities()
        parts.append(f"## Recent Conversation\n\n{conv_section}")

        # 3. Previous Understand decisions (table format)
        if self.decision_history:
            log_section = self._format_decision_log()
            parts.append(f"## Your Previous Decisions\n\nMaintain continuity with past context curation:\n\n{log_section}")

        # 4. Entity Registry with turn tracking (table format)
        registry_section = self._format_entity_registry_table()
        parts.append(registry_section)

        # 5. Pending clarification context (if any)
        if self.pending_clarification:
            parts.append(f"## Pending Clarification\n\nYou previously asked: {self.pending_clarification}")

        return "\n\n---\n\n".join(parts)

    def _format_conversation_with_entities(self, limit: int = 5) -> str:
        """Format conversation history with entity annotations per turn."""
        if not self.recent_turns:
            return "*No previous conversation.*"

        recent = self.recent_turns[-limit:]
        lines = []

        # Calculate turn numbers (working backwards from current)
        start_turn = max(1, self.current_turn - len(recent))

        for i, turn in enumerate(recent):
            turn_num = start_turn + i
            turns_ago = self.current_turn - turn_num
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

            # Show entities mentioned/affected this turn
            turn_entities = self._get_entities_for_turn(turn_num)
            if turn_entities:
                lines.append(f"**Entities:** {', '.join(turn_entities)}")

            lines.append("")

        return "\n".join(lines)

    def _get_entities_for_turn(self, turn_num: int) -> list[str]:
        """Get entity annotations for a specific turn."""
        entities = []
        ref_to_uuid = self.registry_data.get("ref_to_uuid", {})
        ref_turn_created = self.registry_data.get("ref_turn_created", {})
        ref_turn_last_ref = self.registry_data.get("ref_turn_last_ref", {})
        ref_actions = self.registry_data.get("ref_actions", {})
        ref_labels = self.registry_data.get("ref_labels", {})

        for ref in ref_to_uuid.keys():
            created_turn = ref_turn_created.get(ref, 0)
            last_ref_turn = ref_turn_last_ref.get(ref, 0)
            action = ref_actions.get(ref, "")
            label = ref_labels.get(ref, ref)

            if created_turn == turn_num:
                entities.append(f"`{ref}`: {label} ({action})")
            elif last_ref_turn == turn_num and created_turn != turn_num:
                entities.append(f"`{ref}`: {label} (referenced)")

        return entities

    def _format_decision_log(self, limit: int = 10) -> str:
        """Format previous Understand decisions as table."""
        if not self.decision_history:
            return "*No previous context decisions.*"

        recent = self.decision_history[-limit:]
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

    def _format_entity_registry_table(self) -> str:
        """Format entity registry with turn tracking (tabular format)."""
        ref_to_uuid = self.registry_data.get("ref_to_uuid", {})

        if not ref_to_uuid:
            return "## Entity Registry\n\n*No entities tracked yet.*"

        lines = ["## Entity Registry (for context decisions)", ""]
        lines.append("**Entity Source Tags:**")
        lines.append("- `created:user` / `updated:user` — User made this change via UI")
        lines.append("- `mentioned:user` — User @-mentioned this entity")
        lines.append("- `read` / `created` / `generated` — Alfred accessed via conversation")
        lines.append("- `linked` — Auto-registered from FK field")
        lines.append("")
        lines.append("| Ref | Type | Label | Last Action | Created | Last Ref |")
        lines.append("|-----|------|-------|-------------|---------|----------|")

        ref_types = self.registry_data.get("ref_types", {})
        ref_labels = self.registry_data.get("ref_labels", {})
        ref_actions = self.registry_data.get("ref_actions", {})
        ref_turn_created = self.registry_data.get("ref_turn_created", {})
        ref_turn_last_ref = self.registry_data.get("ref_turn_last_ref", {})

        # Sort by recency (most recent last_ref first)
        sorted_refs = sorted(
            ref_to_uuid.keys(),
            key=lambda r: ref_turn_last_ref.get(r, 0),
            reverse=True
        )[:20]  # Limit to 20 most recent

        for ref in sorted_refs:
            lines.append(
                f"| `{ref}` | {ref_types.get(ref, '-')} | "
                f"{ref_labels.get(ref, ref)} | {ref_actions.get(ref, '-')} | "
                f"T{ref_turn_created.get(ref, '?')} | T{ref_turn_last_ref.get(ref, '?')} |"
            )

        if len(ref_to_uuid) > 20:
            lines.append(f"*... and {len(ref_to_uuid) - 20} more*")

        return "\n".join(lines)


@dataclass
class ThinkContext:
    """Context for Think's planning decisions.

    Key feature: Recipe detail level tracking to avoid redundant reads.
    Shows `[read:full]` vs `[read:summary]` so Think knows what data Act has.
    """

    current_turn: int
    # Registry data for entity formatting with recipe detail tracking
    registry_data: dict = field(default_factory=dict)
    # Additional context fields (optional, used by full format())
    conversation: ConversationHistory | None = None
    reasoning: ReasoningTrace | None = None
    curation: CurationSummary | None = None

    def format_entity_context(self) -> str:
        """Format entity context for Think prompt with recipe detail tracking.

        Preserves the proven structure from format_for_think_prompt():
        1. Generated Content (pending artifacts)
        2. Recent Context (last 2 turns) with [read:full/summary] tags
        3. Long Term Memory (Understand-retained)
        """
        lines = []

        # Entity Source Legend (helps Think understand context origins)
        lines.append("**Entity Source Tags:**")
        lines.append("- `[created:user]` / `[updated:user]` — User made this change via UI")
        lines.append("- `[mentioned:user]` — User @-mentioned this entity")
        lines.append("- `[read]` / `[created]` / `[generated]` — Alfred accessed via conversation")
        lines.append("- `[linked]` — Auto-registered from FK field")
        lines.append("")

        ref_to_uuid = self.registry_data.get("ref_to_uuid", {})
        ref_types = self.registry_data.get("ref_types", {})
        ref_labels = self.registry_data.get("ref_labels", {})
        ref_actions = self.registry_data.get("ref_actions", {})
        ref_turn_last_ref = self.registry_data.get("ref_turn_last_ref", {})
        ref_active_reason = self.registry_data.get("ref_active_reason", {})
        ref_turn_created = self.registry_data.get("ref_turn_created", {})
        pending_artifacts = self.registry_data.get("pending_artifacts", {})
        # Recipe detail tracking
        ref_recipe_last_read_level = self.registry_data.get("ref_recipe_last_read_level", {})
        ref_recipe_last_full_turn = self.registry_data.get("ref_recipe_last_full_turn", {})

        # Get active entities split by source
        recent_refs, retained_refs = self._get_active_entities()

        # V9 UNIFIED: Identify generated entities using same logic as entity.py
        # An entity is "generated" if it has pending data AND action is "generated"
        generated_refs = [
            ref for ref in pending_artifacts
            if ref_actions.get(ref) == "generated"
        ]

        # Section 1: Generated content (user hasn't saved yet)
        if generated_refs:
            lines.append("## Generated Content")
            lines.append("**Act has full data for these.** Use `analyze` or `generate` directly (no read needed).")
            lines.append("")
            for ref in generated_refs:
                artifact = pending_artifacts[ref]
                label = artifact.get("name") or artifact.get("label") or ref
                entity_type = ref_types.get(ref, "unknown")
                lines.append(f"- `{ref}`: {label} ({entity_type}) [unsaved]")
            lines.append("")

        if not ref_to_uuid and not pending_artifacts:
            if not lines:
                lines.append("## Available Items")
                lines.append("")
            lines.append("*No entities tracked.*")
            return "\n".join(lines)

        # Section 2: Recent Context (last 2 turns - automatic)
        # Filter out: entities shown in Generated Content section
        recent_display = [r for r in recent_refs if r not in generated_refs]
        if recent_display:
            lines.append("## Recent Context (last 2 turns)")
            lines.append("Act has data for these entities. Check the `[action:level]` tag:")
            lines.append("- `[read:full]` → Act has instructions/ingredients, can `analyze` directly")
            lines.append("- `[read:summary]` → Act has metadata only, `read with instructions` first for details")
            lines.append("")
            for ref in recent_display:
                label = ref_labels.get(ref, ref)
                entity_type = ref_types.get(ref, "unknown")
                action = ref_actions.get(ref, "-")
                last_ref = ref_turn_last_ref.get(ref, "?")
                # Recipe detail level tracking
                if entity_type == "recipe":
                    level = ref_recipe_last_read_level.get(ref)
                    if level:
                        action = f"{action}:{level}"
                        if level != "full":
                            last_full_turn = ref_recipe_last_full_turn.get(ref)
                            if last_full_turn:
                                action = f"{action} (last_full:T{last_full_turn})"
                lines.append(f"- `{ref}`: {label} ({entity_type}) [{action}] T{last_ref}")
            lines.append("")

        # Section 3: Long Term Memory (Understand-retained)
        if retained_refs:
            lines.append("## Long Term Memory (retained from earlier)")
            lines.append("")
            for ref in retained_refs:
                label = ref_labels.get(ref, ref)
                entity_type = ref_types.get(ref, "unknown")
                action = ref_actions.get(ref, "-")
                last_ref = ref_turn_last_ref.get(ref, "?")
                reason = ref_active_reason.get(ref, "")
                reason_note = f" — *{reason}*" if reason else ""
                lines.append(f"- `{ref}`: {label} ({entity_type}) [{action}] T{last_ref}{reason_note}")
            lines.append("")

        # If nothing in either section but we have entities, show summary
        if not recent_refs and not retained_refs and ref_to_uuid:
            lines.append("## Background Entities")
            lines.append("")
            lines.append(f"*{len(ref_to_uuid)} entities tracked but none currently active.*")
            lines.append("*(Use entity refs from conversation to access them.)*")
            lines.append("")

        return "\n".join(lines)

    def _get_active_entities(self, turns_window: int = 2) -> tuple[list[str], list[str]]:
        """Get active entities split into recent vs retained.

        Returns:
            (recent_refs, retained_refs) - Recent are automatic, retained are LLM-curated
        """
        ref_to_uuid = self.registry_data.get("ref_to_uuid", {})
        ref_turn_last_ref = self.registry_data.get("ref_turn_last_ref", {})
        ref_active_reason = self.registry_data.get("ref_active_reason", {})

        recent = []
        retained = []

        for ref in ref_to_uuid.keys():
            last_ref = ref_turn_last_ref.get(ref, 0)
            turns_ago = self.current_turn - last_ref

            if turns_ago <= turns_window:
                recent.append(ref)
            elif ref in ref_active_reason:
                retained.append(ref)

        return recent, retained

    def format(self) -> str:
        """Format full context for Think prompt (entity + conversation + reasoning)."""
        sections = []

        # Entity context with recipe detail tracking
        entity_section = self.format_entity_context()
        if entity_section and "No entities" not in entity_section:
            sections.append(entity_section)

        # Conversation history (full + pending)
        if self.conversation:
            conv_section = format_conversation(self.conversation, depth=2, include_pending=True)
            if conv_section:
                sections.append(f"## Conversation History\n\n{conv_section}")

        # Reasoning trace (what happened last turn)
        if self.reasoning:
            reasoning_section = format_reasoning(self.reasoning, node="think")
            if reasoning_section and "No prior" not in reasoning_section:
                sections.append(f"## What Happened Last Turn\n\n{reasoning_section}")

        # Current turn's curation (from Understand)
        if self.curation:
            curation_section = format_curation_for_think(self.curation)
            if curation_section:
                sections.append(curation_section)

        return "\n\n".join(sections)


@dataclass
class ReplyContext:
    """Context for Reply's response generation."""

    entity: EntityContext
    conversation: ConversationHistory
    reasoning: ReasoningTrace
    execution_outcome: str  # What was accomplished
    pending_artifacts: dict  # V9: Full content of generated artifacts (unified view)

    def format(self) -> str:
        """Format context for Reply prompt."""
        sections = []

        # Entity context with saved/generated distinction
        # Reply needs to know: recipe_3 = saved, gen_recipe_1 = not saved
        entity_section = format_entity_context(self.entity, mode="reply")
        if entity_section and "No entities" not in entity_section:
            sections.append(f"## Entity Context\n\n{entity_section}")

        # V9 UNIFIED: Include generated content so Reply can display it
        # This gives Reply the same view as Think and Act
        if self.pending_artifacts:
            import json
            gen_lines = ["## Generated Content (Full Data)"]
            gen_lines.append("Use this to show users the actual content when requested.")
            gen_lines.append("")
            for ref, content in self.pending_artifacts.items():
                label = content.get("name") or content.get("title") or ref
                gen_lines.append(f"### {ref}: {label}")
                gen_lines.append("```json")
                gen_lines.append(json.dumps(content, indent=2, default=str))
                gen_lines.append("```")
                gen_lines.append("")
            sections.append("\n".join(gen_lines))

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

    Combines best of both worlds:
    - Conversation history with entity annotations per turn
    - Tabular entity registry with turn tracking (T{created}, T{last_ref})
    - Decision history for curation continuity
    """
    from alfred.core.id_registry import SessionIdRegistry

    conversation = state.get("conversation", {})
    current_turn = state.get("current_turn", 1)

    # Get registry data as dict for formatting
    registry_data = state.get("id_registry")
    if registry_data is None:
        registry_dict = {}
    elif isinstance(registry_data, SessionIdRegistry):
        registry_dict = registry_data.to_dict()
    elif isinstance(registry_data, dict):
        registry_dict = registry_data
    else:
        registry_dict = {}

    return UnderstandContext(
        user_message=state.get("user_message", ""),
        current_turn=current_turn,
        recent_turns=conversation.get("recent_turns", []),
        decision_history=conversation.get("understand_decision_log", []),
        pending_clarification=conversation.get("pending_clarification"),
        registry_data=registry_dict,
    )


def build_think_context(state: "AlfredState") -> ThinkContext:
    """
    Build context for Think's planning decisions.

    Key features:
    - Recipe detail level tracking ([read:full] vs [read:summary])
    - Entity refs + labels with action status
    - Reasoning trace from prior turns
    - Current turn's Understand curation decisions
    """
    from alfred.core.id_registry import SessionIdRegistry

    conversation = state.get("conversation", {})
    current_turn = state.get("current_turn", 1)

    # Get registry data as dict for formatting
    registry_data = state.get("id_registry")
    if registry_data is None:
        registry_dict = {}
    elif isinstance(registry_data, SessionIdRegistry):
        registry_dict = registry_data.to_dict()
    elif isinstance(registry_data, dict):
        registry_dict = registry_data
    else:
        registry_dict = {}

    return ThinkContext(
        current_turn=current_turn,
        registry_data=registry_dict,
        conversation=get_conversation_history(conversation),
        reasoning=get_reasoning_trace(conversation),
        curation=get_current_turn_curation(state),
    )


def build_reply_context(state: "AlfredState") -> ReplyContext:
    """
    Build context for Reply's response generation.

    Includes:
    - Entity refs + labels with saved/generated status (so Reply knows what to offer saving)
    - Conversation with engagement summary
    - Reasoning trace (phase, user expressed)
    - Execution outcome summary
    - V9: Full pending_artifacts content (unified view with Think/Act)
    """
    from alfred.core.id_registry import SessionIdRegistry

    conversation = state.get("conversation", {})
    registry = state.get("id_registry", {})
    current_turn = state.get("current_turn", 0)

    # Build execution outcome from step_results
    step_results = state.get("step_results", {})
    think_output = state.get("think_output")
    outcome = _build_execution_outcome(step_results, think_output)

    # V9 UNIFIED: Get pending_artifacts so Reply has same view as Think/Act
    # This enables Reply to show generated content when user asks "show me that recipe"
    pending_artifacts = {}
    if isinstance(registry, SessionIdRegistry):
        pending_artifacts = registry.get_all_pending_artifacts()
    elif isinstance(registry, dict):
        pending_artifacts = registry.get("pending_artifacts", {})

    return ReplyContext(
        entity=get_entity_context(registry, current_turn, mode="reply"),
        conversation=get_conversation_history(conversation),
        reasoning=get_reasoning_trace(conversation),
        execution_outcome=outcome,
        pending_artifacts=pending_artifacts,
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
