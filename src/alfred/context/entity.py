"""
Alfred Context API - Layer 1: Entity Context.

Provides structured access to entities from SessionIdRegistry.

Entity tiers:
- Active: Referenced in last 2 turns (automatic)
- Generated: Created but not saved (pending artifacts)
- Retained: Older entities kept by Understand (with reasons)
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alfred.core.id_registry import SessionIdRegistry


@dataclass
class EntitySnapshot:
    """Snapshot of an entity for context injection."""
    
    ref: str                    # "recipe_1"
    entity_type: str            # "recipes"
    label: str                  # "Lemon Herb Chicken"
    status: str                 # "read" | "created" | "generated" | "linked"
    turn_created: int           # When first seen
    turn_last_ref: int          # When last referenced
    retention_reason: str | None = None  # Why Understand kept it (if retained)


@dataclass
class EntityContext:
    """
    Structured entity context for prompt injection.
    
    Split into tiers for different node needs:
    - active: Recently referenced (automatic 2-turn window)
    - generated: Pending artifacts (not yet saved)
    - retained: Older entities with explicit retention reasons
    """
    
    active: list[EntitySnapshot] = field(default_factory=list)
    generated: list[EntitySnapshot] = field(default_factory=list)
    retained: list[EntitySnapshot] = field(default_factory=list)
    current_turn: int = 0


def get_entity_context(
    registry: "SessionIdRegistry | dict",
    current_turn: int | None = None,
    mode: str = "full",
) -> EntityContext:
    """
    Build entity context from SessionIdRegistry.
    
    Args:
        registry: SessionIdRegistry instance or dict from state
        current_turn: Current turn number (uses registry's if not provided)
        mode: Detail level
            - "full": All data (for Act)
            - "refs_and_labels": Refs + labels only (for Think)
            - "labels_only": Just labels (for Reply)
            - "curation": Full + reasons (for Understand)
    
    Returns:
        EntityContext with entities split by tier
    """
    # Handle dict (from serialized state) vs object
    if isinstance(registry, dict):
        return _get_entity_context_from_dict(registry, current_turn, mode)
    
    # Use registry's current turn if not provided
    if current_turn is None:
        current_turn = registry.current_turn
    
    ctx = EntityContext(current_turn=current_turn)
    
    # Get active entities (recent + retained)
    recent_refs, retained_refs = registry.get_active_entities(turns_window=2)
    
    # Get generated/pending artifacts
    generated_refs = registry.get_generated_pending()
    
    # Build snapshots for each tier
    for ref in recent_refs:
        if ref not in generated_refs:  # Don't duplicate
            snapshot = _build_snapshot(registry, ref)
            ctx.active.append(snapshot)
    
    for ref in generated_refs:
        snapshot = _build_snapshot(registry, ref)
        ctx.generated.append(snapshot)
    
    for ref in retained_refs:
        snapshot = _build_snapshot(registry, ref)
        snapshot.retention_reason = registry.ref_active_reason.get(ref)
        ctx.retained.append(snapshot)
    
    return ctx


def _get_entity_context_from_dict(
    registry_dict: dict,
    current_turn: int | None,
    mode: str,
) -> EntityContext:
    """Build entity context from serialized registry dict."""
    turn = current_turn or registry_dict.get("current_turn", 0)
    ctx = EntityContext(current_turn=turn)
    
    ref_to_uuid = registry_dict.get("ref_to_uuid", {})
    ref_labels = registry_dict.get("ref_labels", {})
    ref_types = registry_dict.get("ref_types", {})
    ref_actions = registry_dict.get("ref_actions", {})
    ref_turn_created = registry_dict.get("ref_turn_created", {})
    ref_turn_last_ref = registry_dict.get("ref_turn_last_ref", {})
    ref_active_reason = registry_dict.get("ref_active_reason", {})
    pending_artifacts = registry_dict.get("pending_artifacts", {})
    
    for ref in ref_to_uuid.keys():
        last_ref_turn = ref_turn_last_ref.get(ref, 0)
        is_recent = (turn - last_ref_turn) <= 2
        is_generated = ref.startswith("gen_") and ref_actions.get(ref) == "generated"
        is_retained = ref in ref_active_reason
        
        snapshot = EntitySnapshot(
            ref=ref,
            entity_type=ref_types.get(ref, "unknown"),
            label=ref_labels.get(ref, ref),
            status=ref_actions.get(ref, "read"),
            turn_created=ref_turn_created.get(ref, 0),
            turn_last_ref=last_ref_turn,
            retention_reason=ref_active_reason.get(ref) if is_retained else None,
        )
        
        if is_generated:
            ctx.generated.append(snapshot)
        elif is_retained and not is_recent:
            ctx.retained.append(snapshot)
        elif is_recent:
            ctx.active.append(snapshot)
    
    return ctx


def _build_snapshot(registry: "SessionIdRegistry", ref: str) -> EntitySnapshot:
    """Build a snapshot for a single ref."""
    return EntitySnapshot(
        ref=ref,
        entity_type=registry.ref_types.get(ref, "unknown"),
        label=registry.ref_labels.get(ref, ref),
        status=registry.ref_actions.get(ref, "read"),
        turn_created=registry.ref_turn_created.get(ref, 0),
        turn_last_ref=registry.ref_turn_last_ref.get(ref, 0),
    )


def format_entity_context(ctx: EntityContext, mode: str = "full") -> str:
    """
    Format entity context for prompt injection.
    
    Args:
        ctx: EntityContext to format
        mode: Detail level
            - "full": Full data with types and status
            - "refs_and_labels": Just refs and labels (for Think)
            - "labels_only": Just labels (for Reply)
            - "do_not_read": Format as "already in context" list for Think
    
    Returns:
        Formatted string for prompt injection
    """
    lines = []
    
    # Generated content (user hasn't saved yet)
    if ctx.generated:
        lines.append("### Generated Content")
        for e in ctx.generated:
            status = "[saved]" if e.status == "created" else "[unsaved]"
            lines.append(f"- `{e.ref}`: {e.label} {status}")
        lines.append("")
    
    # Active (recent context)
    if ctx.active:
        if mode == "do_not_read":
            lines.append("### Already in Context (do not re-read)")
            refs_by_type: dict[str, list[str]] = {}
            for e in ctx.active:
                refs_by_type.setdefault(e.entity_type, []).append(f"{e.ref} ({e.label})")
            for entity_type, refs in refs_by_type.items():
                lines.append(f"- **{entity_type}**: {', '.join(refs)}")
        elif mode == "labels_only":
            lines.append("### Recent Context")
            for e in ctx.active:
                lines.append(f"- {e.label}")
        elif mode == "refs_and_labels":
            lines.append("### Recent Context")
            for e in ctx.active:
                lines.append(f"- `{e.ref}`: {e.label}")
        else:  # full
            lines.append("### Recent Context (last 2 turns)")
            for e in ctx.active:
                lines.append(f"- `{e.ref}`: {e.label} ({e.entity_type}, {e.status})")
        lines.append("")
    
    # Retained (long-term memory)
    if ctx.retained:
        lines.append("### Long-Term Memory")
        for e in ctx.retained:
            reason = f" — {e.retention_reason}" if e.retention_reason else ""
            if mode == "labels_only":
                lines.append(f"- {e.label}")
            elif mode in ("refs_and_labels", "do_not_read"):
                lines.append(f"- `{e.ref}`: {e.label}{reason}")
            else:
                lines.append(f"- `{e.ref}`: {e.label} ({e.entity_type}){reason}")
        lines.append("")
    
    if not lines:
        return "No entities in context."
    
    return "\n".join(lines).strip()
