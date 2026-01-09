"""
Alfred V4 - Session ID Registry.

The core system layer that ensures LLMs never see UUIDs.

ARCHITECTURE:
- Registry persists across turns within a session
- CRUD layer populates registry when db_read/db_create returns data
- All LLM prompts use simple refs (recipe_1, inv_5)
- Translation is 100% deterministic (pure lookup, no LLM inference)

Ref Naming:
- {type}_{n}: Entity from database (recipe_1, inv_5)
- gen_{type}_{n}: Generated but not yet saved (gen_recipe_1)

See docs/session-id-registry-spec.md for full architecture.
"""

from dataclasses import dataclass, field
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionIdRegistry:
    """
    Session-scoped registry for ID translation.
    
    PERSISTS ACROSS TURNS. All CRUD operations flow through this layer.
    LLMs never see UUIDs - only simple refs like recipe_1, inv_5.
    
    Populated by:
    - CRUD layer on db_read output (assigns refs to returned entities)
    - CRUD layer on db_create output (assigns refs to newly created entities)
    - Act node on generate step output (assigns gen_* refs)
    
    Used by:
    - CRUD layer on db_update/db_delete input (translates refs to UUIDs)
    - Prompt formatting (displays refs, never UUIDs)
    """
    
    session_id: str = ""
    
    # ref → UUID mapping (persists across turns)
    ref_to_uuid: dict[str, str] = field(default_factory=dict)
    
    # UUID → ref mapping (for reverse lookups)
    uuid_to_ref: dict[str, str] = field(default_factory=dict)
    
    # Counters per entity type (for generating sequential refs)
    counters: dict[str, int] = field(default_factory=dict)
    
    # Track generated refs separately (gen_recipe_1, etc.)
    gen_counters: dict[str, int] = field(default_factory=dict)
    
    # V4: Store FULL CONTENT of generated artifacts (persists until saved or discarded)
    # Maps gen_* refs to their full artifact content
    # This is what allows cross-turn "generate now, save later" flow
    pending_artifacts: dict[str, dict] = field(default_factory=dict)
    
    # V4: Deterministic action tracking per ref
    # Set by CRUD layer, not LLMs - 100% deterministic
    # Values: "read", "created", "updated", "deleted", "generated"
    ref_actions: dict[str, str] = field(default_factory=dict)
    
    # V4: Labels per ref (for display)
    ref_labels: dict[str, str] = field(default_factory=dict)
    
    # V4: Entity type per ref
    ref_types: dict[str, str] = field(default_factory=dict)
    
    # V4 CONSOLIDATION: Temporal tracking (replaces EntityContextModel/WorkingSet)
    ref_turn_created: dict[str, int] = field(default_factory=dict)   # When first seen
    ref_turn_last_ref: dict[str, int] = field(default_factory=dict)  # When last referenced
    ref_source_step: dict[str, int] = field(default_factory=dict)    # Which step created it
    
    # Current turn number (set by nodes at start of turn)
    current_turn: int = 0
    
    # =========================================================================
    # Ref Generation
    # =========================================================================
    
    def _next_ref(self, entity_type: str) -> str:
        """Generate next ref for a database entity."""
        self.counters[entity_type] = self.counters.get(entity_type, 0) + 1
        return f"{entity_type}_{self.counters[entity_type]}"
    
    def _next_gen_ref(self, entity_type: str) -> str:
        """Generate next ref for a generated (not yet saved) entity."""
        self.gen_counters[entity_type] = self.gen_counters.get(entity_type, 0) + 1
        return f"gen_{entity_type}_{self.gen_counters[entity_type]}"
    
    def _find_matching_pending_artifact(self, entity_type: str, label: str) -> str | None:
        """
        Find a pending gen_* ref that matches entity type and label.
        
        This enables automatic promotion of generated entities when saved:
        - Gen step creates gen_recipe_1 with name "Butter Chicken"
        - Write step saves to DB, CRUD calls register_created(None, uuid, "recipe", "Butter Chicken")
        - This method finds gen_recipe_1 by matching type and label
        - Result: gen_recipe_1 is promoted (not a new recipe_3 created)
        """
        if not label:
            return None
        
        label_lower = label.lower().strip()
        gen_prefix = f"gen_{entity_type}_"
        
        for ref in self.pending_artifacts.keys():
            if not ref.startswith(gen_prefix):
                continue
            
            # Match by stored label
            ref_label = self.ref_labels.get(ref, "")
            if ref_label and ref_label.lower().strip() == label_lower:
                logger.info(f"SessionRegistry: Found pending match {ref} for '{label}'")
                return ref
            
            # Also check artifact content name/title
            artifact = self.pending_artifacts.get(ref, {})
            if isinstance(artifact, dict):
                artifact_name = artifact.get("name") or artifact.get("title") or ""
                if artifact_name and artifact_name.lower().strip() == label_lower:
                    logger.info(f"SessionRegistry: Found pending match {ref} (via content) for '{label}'")
                    return ref
        
        return None
    
    # =========================================================================
    # Output Translation (DB → LLM) - Called by CRUD layer
    # =========================================================================
    
    def translate_read_output(
        self, 
        records: list[dict], 
        table: str,
    ) -> list[dict]:
        """
        Translate DB read results for LLM consumption.
        
        Called by CRUD layer AFTER db_read executes.
        Replaces UUID id fields with simple refs.
        Persists mappings for cross-turn reference.
        """
        if not records:
            return records
        
        entity_type = self._table_to_type(table)
        fk_fields = self._get_fk_fields(table)
        translated = []
        
        for record in records:
            new_record = record.copy()
            
            # Translate primary ID
            if "id" in record and record["id"]:
                uuid = str(record["id"])
                
                # Check if we already have a ref for this UUID (from prior turn)
                if uuid in self.uuid_to_ref:
                    ref = self.uuid_to_ref[uuid]
                else:
                    # Assign new ref and persist
                    ref = self._next_ref(entity_type)
                    self.ref_to_uuid[ref] = uuid
                    self.uuid_to_ref[uuid] = ref
                    logger.info(f"SessionRegistry: Assigned {ref} → {uuid[:8]}...")
                
                new_record["id"] = ref
                
                # V4: Track action, label, type DETERMINISTICALLY
                self.ref_actions[ref] = "read"
                self.ref_types[ref] = entity_type
                label = record.get("name") or record.get("title") or ref
                self.ref_labels[ref] = str(label)
                
                # V4 CONSOLIDATION: Temporal tracking
                if ref not in self.ref_turn_created:
                    self.ref_turn_created[ref] = self.current_turn
                self.ref_turn_last_ref[ref] = self.current_turn
            
            # Translate FK fields (if we have mappings)
            for fk_field in fk_fields:
                if fk_field in record and record[fk_field]:
                    fk_uuid = str(record[fk_field])
                    if fk_uuid in self.uuid_to_ref:
                        new_record[fk_field] = self.uuid_to_ref[fk_uuid]
            
            translated.append(new_record)
        
        return translated
    
    def register_generated(
        self,
        entity_type: str,
        label: str | None = None,
        content: dict | None = None,
        source_step: int | None = None,
    ) -> str:
        """
        Register a generated entity (not yet saved to DB).
        
        Called by Act after generate step produces content.
        Returns a gen_* ref that persists until the entity is saved.
        
        CRITICAL: Stores the full artifact content so it persists across turns.
        When user says "save" in a later turn, Act can retrieve this content.
        """
        ref = self._next_gen_ref(entity_type)
        # No UUID yet - mark as pending
        self.ref_to_uuid[ref] = f"__pending__{ref}"
        
        # V4: Track action, label, type DETERMINISTICALLY
        self.ref_actions[ref] = "generated"
        self.ref_types[ref] = entity_type
        self.ref_labels[ref] = label or ref
        
        # V4 CONSOLIDATION: Temporal tracking
        self.ref_turn_created[ref] = self.current_turn
        self.ref_turn_last_ref[ref] = self.current_turn
        if source_step is not None:
            self.ref_source_step[ref] = source_step
        
        # Store the full content for cross-turn persistence
        if content:
            self.pending_artifacts[ref] = content
            logger.info(f"SessionRegistry: Generated {ref} with content (pending)")
        else:
            logger.info(f"SessionRegistry: Generated {ref} (pending, no content)")
        
        return ref
    
    def get_artifact_content(self, ref: str) -> dict | None:
        """
        Retrieve the full content of a generated artifact.
        
        Called when Act needs to save content that was generated in a prior turn.
        Returns None if ref not found or content was already saved.
        """
        return self.pending_artifacts.get(ref)
    
    def get_all_pending_artifacts(self) -> dict[str, dict]:
        """
        Get all unsaved generated artifacts.
        
        Called by prompt formatting to show "Content to Save" section.
        """
        return self.pending_artifacts.copy()
    
    def register_created(
        self,
        gen_ref: str | None,
        uuid: str,
        entity_type: str,
        label: str | None = None,
    ) -> str:
        """
        Register a newly created entity after db_create.
        
        Called by CRUD layer AFTER db_create executes.
        If gen_ref provided, updates that mapping. Otherwise:
        1. Try to find a matching pending gen_* artifact by type+label
        2. If found, promote it (gen_recipe_1 stays but now points to real UUID)
        3. If not found, create new ref
        
        This ensures gen_recipe_1 → saved recipe uses the SAME ref, not a new recipe_3.
        """
        uuid = str(uuid)
        
        # If no explicit gen_ref, try to find matching pending artifact
        if not gen_ref and label:
            gen_ref = self._find_matching_pending_artifact(entity_type, label)
        
        if gen_ref and gen_ref in self.ref_to_uuid:
            # PROMOTE: Update the gen_* ref to point to real UUID
            old_value = self.ref_to_uuid[gen_ref]
            self.ref_to_uuid[gen_ref] = uuid
            self.uuid_to_ref[uuid] = gen_ref
            
            # V4: Update action to "created" (was "generated")
            self.ref_actions[gen_ref] = "created"
            if label:
                self.ref_labels[gen_ref] = label
            
            # V4 CONSOLIDATION: Update last ref time
            self.ref_turn_last_ref[gen_ref] = self.current_turn
            
            # Clear the pending artifact content - it's now saved in DB
            if gen_ref in self.pending_artifacts:
                del self.pending_artifacts[gen_ref]
                logger.info(f"SessionRegistry: PROMOTED {gen_ref} → {uuid[:8]}... (saved, pending cleared)")
            else:
                logger.info(f"SessionRegistry: PROMOTED {gen_ref} → {uuid[:8]}... (saved)")
            return gen_ref
        else:
            # Create new ref (no matching pending artifact found)
            ref = self._next_ref(entity_type)
            self.ref_to_uuid[ref] = uuid
            self.uuid_to_ref[uuid] = ref
            
            # V4: Track action, label, type DETERMINISTICALLY
            self.ref_actions[ref] = "created"
            self.ref_types[ref] = entity_type
            self.ref_labels[ref] = label or ref
            
            # V4 CONSOLIDATION: Temporal tracking
            self.ref_turn_created[ref] = self.current_turn
            self.ref_turn_last_ref[ref] = self.current_turn
            
            logger.info(f"SessionRegistry: {ref} → {uuid[:8]}... (created, no pending match)")
            return ref
    
    def register_batch_created(
        self,
        gen_refs: list[str] | None,
        uuids: list[str],
        entity_type: str,
    ) -> list[str]:
        """
        Register multiple created entities after batch db_create.
        
        Matches by order if gen_refs provided.
        """
        result_refs = []
        gen_refs = gen_refs or []
        
        for i, uuid in enumerate(uuids):
            gen_ref = gen_refs[i] if i < len(gen_refs) else None
            ref = self.register_created(gen_ref, uuid, entity_type)
            result_refs.append(ref)
        
        return result_refs
    
    # =========================================================================
    # Input Translation (LLM → DB) - Called by CRUD layer
    # =========================================================================
    
    def translate_filters(self, filters: list[dict]) -> list[dict]:
        """
        Translate filter values from refs to UUIDs.
        
        Called by CRUD layer BEFORE db_read/db_update/db_delete executes.
        Pure lookup - no LLM inference.
        """
        if not filters:
            return filters
        
        translated = []
        
        for f in filters:
            new_filter = f.copy()
            value = f.get("value")
            
            if isinstance(value, str):
                if self._is_ref(value):
                    uuid = self.ref_to_uuid.get(value)
                    if uuid and not uuid.startswith("__pending__"):
                        new_filter["value"] = uuid
                    else:
                        logger.warning(f"SessionRegistry: No UUID for ref {value}")
            elif isinstance(value, list):
                new_values = []
                for v in value:
                    if isinstance(v, str) and self._is_ref(v):
                        uuid = self.ref_to_uuid.get(v)
                        if uuid and not uuid.startswith("__pending__"):
                            new_values.append(uuid)
                        else:
                            logger.warning(f"SessionRegistry: No UUID for ref {v}")
                            new_values.append(v)  # Keep original on failure
                    else:
                        new_values.append(v)
                new_filter["value"] = new_values
            
            translated.append(new_filter)
        
        return translated
    
    def translate_payload(self, data: dict, table: str) -> dict:
        """
        Translate FK fields in create/update payload from refs to UUIDs.
        
        Called by CRUD layer BEFORE db_create/db_update executes.
        """
        if not data:
            return data
        
        translated = data.copy()
        fk_fields = self._get_fk_fields(table)
        
        # Also check common FK patterns
        fk_fields = set(fk_fields) | {"recipe_id", "meal_plan_id", "task_id", 
                                       "ingredient_id", "parent_recipe_id"}
        
        for fk_field in fk_fields:
            if fk_field in translated and translated[fk_field]:
                value = translated[fk_field]
                if isinstance(value, str) and self._is_ref(value):
                    uuid = self.ref_to_uuid.get(value)
                    if uuid and not uuid.startswith("__pending__"):
                        translated[fk_field] = uuid
                    else:
                        logger.warning(f"SessionRegistry: No UUID for FK ref {value}")
        
        return translated
    
    def translate_payload_batch(self, data_list: list[dict], table: str) -> list[dict]:
        """Translate a batch of payloads."""
        return [self.translate_payload(d, table) for d in data_list]
    
    # =========================================================================
    # Lookup Methods
    # =========================================================================
    
    def get_uuid(self, ref: str) -> str | None:
        """Look up UUID for a ref. Returns None if not found or pending."""
        uuid = self.ref_to_uuid.get(ref)
        if uuid and uuid.startswith("__pending__"):
            return None
        return uuid
    
    def get_ref(self, uuid: str) -> str | None:
        """Look up ref for a UUID."""
        return self.uuid_to_ref.get(str(uuid))
    
    def has_ref(self, ref: str) -> bool:
        """Check if a ref is registered."""
        return ref in self.ref_to_uuid
    
    def remove_ref(self, ref: str) -> bool:
        """
        Remove a ref from the registry (e.g., after db_delete).
        Also removes any pending artifact content.
        Returns True if ref was found and removed.
        """
        if ref not in self.ref_to_uuid:
            return False
        
        uuid = self.ref_to_uuid.pop(ref, None)
        if uuid and not uuid.startswith("__pending__"):
            self.uuid_to_ref.pop(uuid, None)
        
        # Also remove pending artifact content
        self.pending_artifacts.pop(ref, None)
        
        logger.info(f"SessionRegistry: Removed {ref}")
        return True
    
    def get_all_refs_for_type(self, entity_type: str) -> list[str]:
        """Get all refs for a specific entity type."""
        prefix = f"{entity_type}_"
        gen_prefix = f"gen_{entity_type}_"
        return [
            ref for ref in self.ref_to_uuid.keys()
            if ref.startswith(prefix) or ref.startswith(gen_prefix)
        ]
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def _is_ref(self, value: str) -> bool:
        """
        Check if a value is a ref (not a UUID).
        
        Refs: recipe_1, gen_recipe_1, inv_5
        UUIDs: a508000d-9b55-40f0-8886-dbdd88bd2de2
        """
        if not isinstance(value, str):
            return False
        
        # UUIDs have specific format: 8-4-4-4-12 hex chars
        if len(value) == 36 and value.count("-") == 4:
            return False
        
        # Refs match pattern: {type}_{n} or gen_{type}_{n}
        if "_" not in value:
            return False
        
        # Check if it looks like our ref format
        parts = value.split("_")
        if len(parts) >= 2:
            # Last part should be a number
            try:
                int(parts[-1])
                return True
            except ValueError:
                pass
        
        return False
    
    def _table_to_type(self, table: str) -> str:
        """Convert table name to entity type (singular, for refs)."""
        mapping = {
            "recipes": "recipe",
            "recipe_ingredients": "ri",  # Short for readability
            "inventory": "inv",
            "shopping_list": "shop",
            "meal_plans": "meal",
            "tasks": "task",
            "preferences": "pref",
            "ingredients": "ing",
        }
        return mapping.get(table, table.rstrip("s"))
    
    def _get_fk_fields(self, table: str) -> list[str]:
        """Get FK fields for a table."""
        fk_map = {
            "recipe_ingredients": ["recipe_id", "ingredient_id"],
            "meal_plans": ["recipe_id"],
            "tasks": ["recipe_id", "meal_plan_id"],
        }
        return fk_map.get(table, [])
    
    # =========================================================================
    # Prompt Formatting
    # =========================================================================
    
    def format_for_prompt(self) -> str:
        """
        Format current registry for debugging/prompt display.
        
        Note: We don't show UUIDs - that's the whole point!
        """
        if not self.ref_to_uuid:
            return "*No entities in registry.*"
        
        # Group by type
        by_type: dict[str, list[str]] = {}
        for ref in self.ref_to_uuid.keys():
            if ref.startswith("gen_"):
                parts = ref.split("_")
                entity_type = parts[1] if len(parts) > 1 else "unknown"
            else:
                parts = ref.split("_")
                entity_type = parts[0] if parts else "unknown"
            
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(ref)
        
        lines = ["## Registered Entities", ""]
        for entity_type, refs in sorted(by_type.items()):
            lines.append(f"**{entity_type}:** {', '.join(sorted(refs))}")
        
        return "\n".join(lines)
    
    def get_stats(self) -> dict:
        """Get registry statistics."""
        return {
            "total_refs": len(self.ref_to_uuid),
            "db_refs": sum(1 for r in self.ref_to_uuid if not r.startswith("gen_")),
            "gen_refs": sum(1 for r in self.ref_to_uuid if r.startswith("gen_")),
            "pending": sum(1 for v in self.ref_to_uuid.values() if v.startswith("__pending__")),
        }
    
    def format_entities_for_prompt(self) -> str:
        """
        Format all tracked entities with their actions for prompt injection.
        
        V4: Deterministic display of what happened to each entity.
        """
        if not self.ref_to_uuid:
            return "No entities tracked."
        
        lines = ["## Entity Registry", ""]
        lines.append("| Ref | Type | Label | Last Action |")
        lines.append("|-----|------|-------|-------------|")
        
        for ref in sorted(self.ref_to_uuid.keys()):
            entity_type = self.ref_types.get(ref, "-")
            label = self.ref_labels.get(ref, ref)
            action = self.ref_actions.get(ref, "-")
            lines.append(f"| `{ref}` | {entity_type} | {label} | {action} |")
        
        return "\n".join(lines)
    
    def get_entities_by_action(self, action: str) -> list[str]:
        """Get all refs with a specific action."""
        return [ref for ref, act in self.ref_actions.items() if act == action]
    
    # =========================================================================
    # V4 CONSOLIDATION: View Methods (replace WorkingSet, EntityContextModel)
    # These are presentation logic, not separate data stores
    # =========================================================================
    
    def set_turn(self, turn: int) -> None:
        """Set the current turn number. Called at start of each turn."""
        self.current_turn = turn
    
    def touch_ref(self, ref: str) -> None:
        """Mark a ref as referenced this turn (updates last_ref)."""
        if ref in self.ref_to_uuid:
            self.ref_turn_last_ref[ref] = self.current_turn
    
    def get_entities_this_turn(self) -> list[str]:
        """Get all refs created or referenced this turn."""
        return [
            ref for ref in self.ref_to_uuid.keys()
            if self.ref_turn_last_ref.get(ref) == self.current_turn
        ]
    
    def get_entities_by_recency(self, limit: int = 20) -> list[str]:
        """Get refs sorted by recency (most recent first)."""
        refs = list(self.ref_to_uuid.keys())
        refs.sort(key=lambda r: self.ref_turn_last_ref.get(r, 0), reverse=True)
        return refs[:limit]
    
    def get_generated_pending(self) -> list[str]:
        """Get all gen_* refs that are still pending (not yet saved)."""
        return [
            ref for ref in self.ref_to_uuid.keys()
            if ref.startswith("gen_") and self.ref_actions.get(ref) == "generated"
        ]
    
    def format_for_act_prompt(self, current_step: int | None = None) -> str:
        """
        Format entities for Act prompt. REPLACES WorkingSet.
        
        Shows:
        - Entities from this turn (most relevant)
        - Generated pending items (need to be saved)
        - Recent entities from prior turns
        """
        lines = ["## Working Set", ""]
        
        # Section 1: Generated pending (highest priority for Act)
        pending = self.get_generated_pending()
        if pending:
            lines.append("### Pending (not yet saved)")
            lines.append("| Ref | Type | Label |")
            lines.append("|-----|------|-------|")
            for ref in pending:
                lines.append(f"| `{ref}` | {self.ref_types.get(ref, '-')} | {self.ref_labels.get(ref, ref)} |")
            lines.append("")
        
        # Section 2: This turn's entities
        this_turn = [r for r in self.get_entities_this_turn() if r not in pending]
        if this_turn:
            lines.append("### This Turn")
            lines.append("| Ref | Type | Label | Action |")
            lines.append("|-----|------|-------|--------|")
            for ref in this_turn:
                lines.append(
                    f"| `{ref}` | {self.ref_types.get(ref, '-')} | "
                    f"{self.ref_labels.get(ref, ref)} | {self.ref_actions.get(ref, '-')} |"
                )
            lines.append("")
        
        # Section 3: Recent from prior turns (context)
        prior_refs = [
            r for r in self.get_entities_by_recency(10)
            if r not in pending and r not in this_turn
        ]
        if prior_refs:
            lines.append("### Prior Turns (for reference)")
            lines.append("| Ref | Type | Label | Last Action | Turn |")
            lines.append("|-----|------|-------|-------------|------|")
            for ref in prior_refs[:5]:  # Limit to 5 from prior turns
                lines.append(
                    f"| `{ref}` | {self.ref_types.get(ref, '-')} | "
                    f"{self.ref_labels.get(ref, ref)} | {self.ref_actions.get(ref, '-')} | "
                    f"{self.ref_turn_last_ref.get(ref, '-')} |"
                )
        
        if len(lines) == 2:  # Just header
            lines.append("*No entities in registry.*")
        
        return "\n".join(lines)
    
    def format_for_understand_prompt(self) -> str:
        """
        Format entities for Understand prompt. REPLACES EntityContextModel.
        
        Shows all tracked entities so Understand can decide what's relevant.
        """
        lines = ["## Entity Registry (for context decisions)", ""]
        
        if not self.ref_to_uuid:
            lines.append("*No entities tracked.*")
            return "\n".join(lines)
        
        lines.append("| Ref | Type | Label | Last Action | Created | Last Ref |")
        lines.append("|-----|------|-------|-------------|---------|----------|")
        
        # Sort by recency
        for ref in self.get_entities_by_recency(20):
            lines.append(
                f"| `{ref}` | {self.ref_types.get(ref, '-')} | "
                f"{self.ref_labels.get(ref, ref)} | {self.ref_actions.get(ref, '-')} | "
                f"T{self.ref_turn_created.get(ref, '?')} | T{self.ref_turn_last_ref.get(ref, '?')} |"
            )
        
        if len(self.ref_to_uuid) > 20:
            lines.append(f"*... and {len(self.ref_to_uuid) - 20} more*")
        
        return "\n".join(lines)
    
    def format_for_think_prompt(self) -> str:
        """
        Format entities for Think prompt.
        
        Shows what's available for planning (so Think knows what exists).
        """
        lines = ["## Entities in Context", ""]
        
        # Show pending artifacts FIRST - these need to be saved!
        if self.pending_artifacts:
            lines.append("**⚠️ Generated (NOT YET SAVED):**")
            for ref, artifact in self.pending_artifacts.items():
                label = artifact.get("name") or artifact.get("label") or ref
                lines.append(f"  - `{ref}`: {label} [generated, needs save]")
            lines.append("")
        
        if not self.ref_to_uuid and not self.pending_artifacts:
            lines.append("*No entities tracked.*")
            return "\n".join(lines)
        
        # Group saved entities by type
        by_type: dict[str, list[str]] = {}
        for ref in self.ref_to_uuid.keys():
            entity_type = self.ref_types.get(ref, "unknown")
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(ref)
        
        for entity_type, refs in sorted(by_type.items()):
            lines.append(f"**{entity_type}s:** ({len(refs)} total)")
            # Show first 5 with details
            for ref in refs[:5]:
                action = self.ref_actions.get(ref, "-")
                label = self.ref_labels.get(ref, ref)
                # Mark if referenced this turn
                this_turn = "← this turn" if self.ref_turn_last_ref.get(ref) == self.current_turn else ""
                lines.append(f"  - `{ref}`: {label} [{action}] {this_turn}")
            if len(refs) > 5:
                lines.append(f"  - *... and {len(refs) - 5} more*")
            lines.append("")
        
        return "\n".join(lines)
    
    # =========================================================================
    # Serialization (for state persistence across turns)
    # =========================================================================
    
    def to_dict(self) -> dict:
        """Serialize for state storage. PERSISTS ACROSS TURNS."""
        return {
            "session_id": self.session_id,
            "ref_to_uuid": self.ref_to_uuid,
            "uuid_to_ref": self.uuid_to_ref,
            "counters": self.counters,
            "gen_counters": self.gen_counters,
            "pending_artifacts": self.pending_artifacts,
            "ref_actions": self.ref_actions,
            "ref_labels": self.ref_labels,
            "ref_types": self.ref_types,
            # V4 CONSOLIDATION: Temporal tracking
            "ref_turn_created": self.ref_turn_created,
            "ref_turn_last_ref": self.ref_turn_last_ref,
            "ref_source_step": self.ref_source_step,
            "current_turn": self.current_turn,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionIdRegistry":
        """Deserialize from dict."""
        registry = cls(session_id=data.get("session_id", ""))
        registry.ref_to_uuid = data.get("ref_to_uuid", {})
        registry.uuid_to_ref = data.get("uuid_to_ref", {})
        registry.counters = data.get("counters", {})
        registry.gen_counters = data.get("gen_counters", {})
        registry.pending_artifacts = data.get("pending_artifacts", {})
        registry.ref_actions = data.get("ref_actions", {})
        registry.ref_labels = data.get("ref_labels", {})
        registry.ref_types = data.get("ref_types", {})
        # V4 CONSOLIDATION: Temporal tracking
        registry.ref_turn_created = data.get("ref_turn_created", {})
        registry.ref_turn_last_ref = data.get("ref_turn_last_ref", {})
        registry.ref_source_step = data.get("ref_source_step", {})
        registry.current_turn = data.get("current_turn", 0)
        return registry


# Backward compatibility alias (will be removed)
TurnIdRegistry = SessionIdRegistry
