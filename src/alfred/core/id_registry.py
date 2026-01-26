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

    # V7: Deterministic recipe detail tracking (what was actually returned by CRUD)
    # This helps Think/Act know whether a recipe was last read with instructions or not.
    # NOTE: This is NOT a guarantee that full data is currently "loaded" for Act; it is only
    # a record of what the last read returned.
    ref_recipe_last_read_level: dict[str, str] = field(default_factory=dict)  # "summary" | "full"
    ref_recipe_last_full_turn: dict[str, int] = field(default_factory=dict)   # turn when instructions were last included
    
    # V4 CONSOLIDATION: Temporal tracking (replaces EntityContextModel/WorkingSet)
    ref_turn_created: dict[str, int] = field(default_factory=dict)   # When first seen
    ref_turn_last_ref: dict[str, int] = field(default_factory=dict)  # When last referenced
    ref_source_step: dict[str, int] = field(default_factory=dict)    # Which step created it
    
    # V4.1: Track when gen_* refs are promoted (saved to DB)
    # Used to show "Just Saved" section and auto-clear at turn end
    ref_turn_promoted: dict[str, int] = field(default_factory=dict)
    
    # Current turn number (set by nodes at start of turn)
    current_turn: int = 0
    
    # V5: Understand context management - stores WHY an older entity is still active
    # Only populated for entities beyond the automatic 2-turn window
    # Example: {"gen_meal_plan_1": "User's ongoing weekly meal plan goal"}
    ref_active_reason: dict[str, str] = field(default_factory=dict)
    
    # V5: Lazy registration enrichment queue
    # Tracks refs that were lazy-registered and need name enrichment
    # Format: {ref: (table_to_query, name_column)}
    # Cleared after enrichment batch runs
    _lazy_enrich_queue: dict[str, tuple[str, str]] = field(default_factory=dict)

    # V10: Change tracking for frontend streaming
    # Tracks last snapshot of active refs to compute diffs
    _last_snapshot_refs: set[str] = field(default_factory=set)
    
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

                # V7: Recipe detail level tracking (summary vs full instructions)
                # Determined purely from the returned DB record shape.
                if entity_type == "recipe":
                    if "instructions" in record:
                        self.ref_recipe_last_read_level[ref] = "full"
                        self.ref_recipe_last_full_turn[ref] = self.current_turn
                    else:
                        self.ref_recipe_last_read_level[ref] = "summary"
                
                # Compute label based on entity type
                label = self._compute_entity_label(record, entity_type, ref)
                self.ref_labels[ref] = str(label)
                
                # V4 CONSOLIDATION: Temporal tracking
                if ref not in self.ref_turn_created:
                    self.ref_turn_created[ref] = self.current_turn
                self.ref_turn_last_ref[ref] = self.current_turn
            
            # Translate FK fields - with lazy registration for unknown UUIDs
            # This is critical: when reading meal_plans, we see recipe_ids for recipes
            # we haven't read yet. Without lazy registration, raw UUIDs leak to the LLM.
            for fk_field in fk_fields:
                if fk_field in record and record[fk_field]:
                    fk_uuid = str(record[fk_field])
                    
                    if fk_uuid in self.uuid_to_ref:
                        # Already known - use existing ref and include label if available
                        fk_ref = self.uuid_to_ref[fk_uuid]
                        new_record[fk_field] = fk_ref
                        # Enrich with label for display (e.g., "Butter Chicken (recipe_1)")
                        label = self.ref_labels.get(fk_ref)
                        if label and label != fk_ref:  # Only if we have a real label
                            new_record[f"_{fk_field}_label"] = label
                    else:
                        # Lazy registration: assign a ref now so LLM never sees raw UUIDs
                        fk_entity_type = self._fk_field_to_type(fk_field)
                        fk_ref = self._next_ref(fk_entity_type)
                        self.ref_to_uuid[fk_ref] = fk_uuid
                        self.uuid_to_ref[fk_uuid] = fk_ref
                        # Mark as "linked" since we discovered it via FK, not direct read
                        self.ref_actions[fk_ref] = "linked"
                        self.ref_types[fk_ref] = fk_entity_type
                        self.ref_labels[fk_ref] = fk_ref  # Placeholder until enriched
                        if fk_ref not in self.ref_turn_created:
                            self.ref_turn_created[fk_ref] = self.current_turn
                        self.ref_turn_last_ref[fk_ref] = self.current_turn
                        new_record[fk_field] = fk_ref
                        
                        # Queue for enrichment if table supports name lookup
                        enrich_info = self._fk_field_to_enrich_info(fk_field)
                        if enrich_info and enrich_info[1]:  # Has name column
                            self._lazy_enrich_queue[fk_ref] = enrich_info
                        
                        logger.info(f"SessionRegistry: Lazy-registered {fk_ref} → {fk_uuid[:8]}... (via {fk_field})")
            
            # Handle nested relations (e.g., recipe_ingredients inside recipes)
            # These need their IDs registered so Act can target them for updates
            if "recipe_ingredients" in record and isinstance(record["recipe_ingredients"], list):
                translated_ingredients = []
                for ing in record["recipe_ingredients"]:
                    if isinstance(ing, dict) and "id" in ing and ing["id"]:
                        ing_copy = ing.copy()
                        ing_uuid = str(ing["id"])
                        
                        if ing_uuid in self.uuid_to_ref:
                            ing_ref = self.uuid_to_ref[ing_uuid]
                        else:
                            ing_ref = self._next_ref("ri")
                            self.ref_to_uuid[ing_ref] = ing_uuid
                            self.uuid_to_ref[ing_uuid] = ing_ref
                            self.ref_actions[ing_ref] = "read"
                            self.ref_types[ing_ref] = "ri"
                            self.ref_labels[ing_ref] = ing.get("name", ing_ref)
                            if ing_ref not in self.ref_turn_created:
                                self.ref_turn_created[ing_ref] = self.current_turn
                            self.ref_turn_last_ref[ing_ref] = self.current_turn
                            logger.info(f"SessionRegistry: Registered nested {ing_ref} → {ing_uuid[:8]}...")
                        
                        ing_copy["id"] = ing_ref
                        translated_ingredients.append(ing_copy)
                    else:
                        # Ingredient without ID (summary view) - keep as-is
                        translated_ingredients.append(ing)
                new_record["recipe_ingredients"] = translated_ingredients
            
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

    # =========================================================================
    # Unified Entity Data Access (V9)
    # =========================================================================

    def get_entity_data(self, ref: str) -> dict | None:
        """
        Unified entity data access - the SINGLE source of truth.

        Works identically for gen_* and regular refs. This is the preferred
        method for checking if entity data is available in the registry.

        Returns:
            - dict: Full entity content if available in registry (from pending_artifacts)
            - None: Data not in registry (need step_results or DB read)

        Note: Regular refs return None because their data lives in step_results,
        not in the registry. This is intentional - we don't duplicate storage.
        """
        return self.pending_artifacts.get(ref)

    def update_entity_data(self, ref: str, content: dict) -> bool:
        """
        Update content of an existing entity in the registry.

        Used when Act modifies a gen_* artifact (e.g., applying user feedback
        like "add feta to that recipe").

        Args:
            ref: Entity reference (e.g., "gen_recipe_1")
            content: New full content to replace existing

        Returns:
            True if entity was updated, False if ref not found in registry
        """
        if ref in self.pending_artifacts:
            self.pending_artifacts[ref] = content
            # Update label if changed
            new_label = content.get("name") or content.get("title")
            if new_label:
                self.ref_labels[ref] = new_label
            logger.info(f"SessionRegistry: Updated entity data for {ref}")
            return True
        return False

    def get_all_pending_artifacts(self) -> dict[str, dict]:
        """
        Get all generated artifacts (including promoted ones).
        
        Called by Act prompt to show "Generated Data" section with full JSON.
        Includes promoted artifacts so Act can access linked record data (e.g., ingredients).
        """
        return self.pending_artifacts.copy()
    
    def get_truly_pending_artifacts(self) -> dict[str, dict]:
        """
        Get artifacts that haven't had their main record created yet.
        
        Filters out artifacts where ref_actions shows 'created'.
        Use this for "Needs Creating" section in prompts.
        """
        return {
            ref: content
            for ref, content in self.pending_artifacts.items()
            if self.ref_actions.get(ref) != "created"
        }
    
    def clear_pending_artifact(self, ref: str) -> bool:
        """
        Explicitly clear a pending artifact after ALL linked records are saved.
        
        Call this after creating both main record and linked records (e.g., recipe + ingredients).
        Returns True if artifact was cleared, False if not found.
        """
        if ref in self.pending_artifacts:
            del self.pending_artifacts[ref]
            logger.info(f"SessionRegistry: Cleared pending artifact {ref}")
            return True
        return False
    
    def get_just_promoted_artifacts(self) -> dict[str, dict]:
        """
        Get artifacts that were promoted (saved) THIS turn.
        
        These have their main record in DB but content is retained for linked records.
        Use for "Just Saved This Turn" section in prompts.
        """
        return {
            ref: content
            for ref, content in self.pending_artifacts.items()
            if self.ref_turn_promoted.get(ref) == self.current_turn
        }
    
    def clear_turn_promoted_artifacts(self) -> int:
        """
        Clear all artifacts that were promoted this turn.
        
        Call at END of turn (in Summarize) to clean up saved content.
        Returns number of artifacts cleared.
        """
        to_clear = [
            ref for ref in self.pending_artifacts
            if self.ref_turn_promoted.get(ref) == self.current_turn
        ]
        for ref in to_clear:
            del self.pending_artifacts[ref]
            logger.info(f"SessionRegistry: Cleared promoted artifact {ref} (turn end)")
        return len(to_clear)
    
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
            
            # V4.1: Track when this ref was promoted (for "Just Saved" section)
            self.ref_turn_promoted[gen_ref] = self.current_turn
            
            # NOTE: Do NOT clear pending_artifacts here!
            # Content retained until turn end for linked records (recipe_ingredients)
            if gen_ref in self.pending_artifacts:
                logger.info(f"SessionRegistry: PROMOTED {gen_ref} → {uuid[:8]}... (saved this turn, content retained)")
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

    def register_from_ui(
        self,
        uuid: str,
        entity_type: str,
        label: str,
        action: str,
    ) -> str:
        """
        Register an entity created/edited via UI.

        Called when processing ui_changes from frontend before Understand runs.
        Handles both new entities and entities already in registry.

        Args:
            uuid: Entity UUID from database
            entity_type: Type like "recipe", "inv", "task"
            label: Human-readable label (e.g., recipe name)
            action: Action tag like "created:user", "updated:user", "deleted:user"

        Returns:
            The ref assigned to this entity
        """
        uuid = str(uuid)

        # Check if already registered
        existing_ref = self.uuid_to_ref.get(uuid)
        if existing_ref:
            # Entity already in registry — just update action and touch
            self.ref_actions[existing_ref] = action
            self.touch_ref(existing_ref)
            if label:
                self.ref_labels[existing_ref] = label
            logger.info(f"SessionRegistry: UI change {existing_ref} [{action}]")
            return existing_ref
        else:
            # New to registry — assign ref
            ref = self._next_ref(entity_type)
            self.ref_to_uuid[ref] = uuid
            self.uuid_to_ref[uuid] = ref
            self.ref_actions[ref] = action
            self.ref_types[ref] = entity_type
            self.ref_labels[ref] = label or ref

            # Temporal tracking
            self.ref_turn_created[ref] = self.current_turn
            self.ref_turn_last_ref[ref] = self.current_turn

            logger.info(f"SessionRegistry: UI registered {ref} → {uuid[:8]}... [{action}]")
            return ref
    
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
    # Lazy Registration Enrichment
    # =========================================================================
    
    def get_lazy_enrich_queue(self) -> dict[str, tuple[str, str, str]]:
        """
        Get refs that need enrichment, grouped by table.
        
        Returns: {ref: (table, name_column, uuid)}
        """
        result = {}
        for ref, (table, name_col) in self._lazy_enrich_queue.items():
            uuid = self.ref_to_uuid.get(ref)
            if uuid and not uuid.startswith("__pending__"):
                result[ref] = (table, name_col, uuid)
        return result
    
    def apply_enrichment(self, enrichments: dict[str, str]) -> None:
        """
        Apply name enrichments to lazy-registered refs.
        
        Args:
            enrichments: {ref: name}
        """
        for ref, name in enrichments.items():
            if ref in self.ref_labels and name:
                old_label = self.ref_labels[ref]
                self.ref_labels[ref] = name
                logger.info(f"SessionRegistry: Enriched {ref}: '{old_label}' → '{name}'")
        
        # Clear the queue after applying
        self._lazy_enrich_queue.clear()
    
    def clear_enrich_queue(self) -> None:
        """Clear the enrichment queue without applying."""
        self._lazy_enrich_queue.clear()
    
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
    
    def _fk_field_to_type(self, fk_field: str) -> str:
        """Convert FK field name to entity type for lazy registration."""
        # FK field naming convention: <entity_type>_id
        fk_type_map = {
            "recipe_id": "recipe",
            "ingredient_id": "ing",
            "meal_plan_id": "meal",
            "task_id": "task",
            "parent_recipe_id": "recipe",
        }
        return fk_type_map.get(fk_field, fk_field.replace("_id", ""))
    
    def _compute_entity_label(self, record: dict, entity_type: str, ref: str) -> str:
        """
        Compute a human-readable label for an entity based on its type.
        
        Different entity types use different fields for their labels:
        - recipes: name
        - tasks: title  
        - meal_plans: date [meal_type]
        - inventory: name
        """
        # Standard name/title fields
        if record.get("name"):
            return record["name"]
        if record.get("title"):
            return record["title"]
        
        # Special handling for meal_plans: "Jan 12 [lunch]"
        if entity_type == "meal" and record.get("date"):
            date = record["date"]
            meal_type = record.get("meal_type", "meal")
            # Try to make date more readable if it's a string
            try:
                from datetime import datetime
                if isinstance(date, str):
                    dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                    date = dt.strftime("%b %d")  # "Jan 12"
            except:
                pass  # Keep original date string
            return f"{date} [{meal_type}]"
        
        return ref
    
    def _fk_field_to_enrich_info(self, fk_field: str) -> tuple[str, str] | None:
        """
        Get (table, name_column) for enriching lazy-registered FK refs.
        
        Returns None if the FK type doesn't support name enrichment.
        """
        # Maps FK field → (target_table, name_column)
        fk_enrich_map = {
            "recipe_id": ("recipes", "name"),
            "ingredient_id": ("ingredients", "name"),
            "meal_plan_id": ("meal_plans", None),  # No single name field
            "task_id": ("tasks", "title"),
            "parent_recipe_id": ("recipes", "name"),
        }
        return fk_enrich_map.get(fk_field)
    
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
    
    def touch_refs_from_step_data(self, data: dict | None, result_summary: str | None = None) -> int:
        """
        Extract and touch any entity refs mentioned in step data or summary.
        
        This ensures that refs mentioned in analyze/generate output stay in
        recent context for subsequent turns.
        
        Returns the count of refs touched.
        """
        import re
        touched = 0
        ref_pattern = re.compile(r'\b(recipe_\d+|inv_\d+|task_\d+|meal_plan_\d+|gen_\w+_\d+)\b')
        
        # Extract from data dict (recursively)
        def extract_refs_from_dict(d: dict | list | str) -> set[str]:
            refs = set()
            if isinstance(d, dict):
                for v in d.values():
                    refs.update(extract_refs_from_dict(v))
            elif isinstance(d, list):
                for item in d:
                    refs.update(extract_refs_from_dict(item))
            elif isinstance(d, str):
                refs.update(ref_pattern.findall(d))
            return refs
        
        all_refs = set()
        if data:
            all_refs.update(extract_refs_from_dict(data))
        if result_summary:
            all_refs.update(ref_pattern.findall(result_summary))
        
        for ref in all_refs:
            if ref in self.ref_to_uuid:
                self.touch_ref(ref)
                touched += 1
        
        if touched:
            logger.debug(f"SessionRegistry: Touched {touched} refs from step data: {all_refs}")
        
        return touched
    
    def get_entities_this_turn(self) -> list[str]:
        """Get all refs created or referenced this turn."""
        return [
            ref for ref in self.ref_to_uuid.keys()
            if self.ref_turn_last_ref.get(ref) == self.current_turn
        ]
    
    def get_active_entities(self, turns_window: int = 2) -> tuple[list[str], list[str]]:
        """
        Get active entities for Think/Act prompts.
        
        Returns:
            (recent_refs, retained_refs):
            - recent_refs: Automatically active (last N turns)
            - retained_refs: Understand-curated (older but still relevant)
        
        This is the core method for context management.
        Recent entities are automatically included based on recency.
        Retained entities are explicitly kept active by Understand.
        """
        recent_refs = []
        retained_refs = []
        
        for ref in self.ref_to_uuid.keys():
            last_ref_turn = self.ref_turn_last_ref.get(ref, 0)
            
            # Automatic: entity referenced within turns_window (inclusive)
            # <= ensures "last 2 turns" includes entities from exactly 2 turns ago
            if self.current_turn - last_ref_turn <= turns_window:
                recent_refs.append(ref)
            # Understand-retained: has an active reason
            elif ref in self.ref_active_reason:
                retained_refs.append(ref)
        
        return recent_refs, retained_refs
    
    def set_active_reason(self, ref: str, reason: str) -> None:
        """
        Mark an older entity as actively retained with a reason.
        
        Called when Understand decides an older entity is still relevant.
        """
        if ref in self.ref_to_uuid:
            self.ref_active_reason[ref] = reason
            logger.info(f"SessionRegistry: Retained {ref} — {reason}")
    
    def clear_active_reason(self, ref: str) -> None:
        """
        Remove active retention for an entity (demote to background).
        
        Called when Understand decides an older entity is no longer relevant.
        """
        if ref in self.ref_active_reason:
            del self.ref_active_reason[ref]
            logger.info(f"SessionRegistry: Demoted {ref} from active")
    
    def get_entities_by_recency(self, limit: int = 20) -> list[str]:
        """Get refs sorted by recency (most recent first)."""
        refs = list(self.ref_to_uuid.keys())
        refs.sort(key=lambda r: self.ref_turn_last_ref.get(r, 0), reverse=True)
        return refs[:limit]

    def get_active_context_for_frontend(self) -> dict:
        """
        Return active entities with full metadata for frontend streaming.

        Includes change tracking to highlight newly added entities.
        Called after each phase that modifies entity context (Understand, Act steps, Reply).
        """
        recent, retained = self.get_active_entities(turns_window=2)
        all_active = set(recent + retained)

        # Compute changes since last snapshot
        added = all_active - self._last_snapshot_refs

        def entity_to_dict(ref: str) -> dict:
            return {
                "ref": ref,
                "type": self.ref_types.get(ref),
                "label": self.ref_labels.get(ref),
                "action": self.ref_actions.get(ref),
                "turnCreated": self.ref_turn_created.get(ref),
                "turnLastRef": self.ref_turn_last_ref.get(ref),
                "isGenerated": ref.startswith("gen_"),
                "retentionReason": self.ref_active_reason.get(ref),
            }

        # Sort by recency (most recent first)
        sorted_refs = sorted(
            all_active,
            key=lambda r: self.ref_turn_last_ref.get(r, 0),
            reverse=True
        )

        # Update snapshot for next diff
        self._last_snapshot_refs = all_active

        return {
            "entities": [entity_to_dict(ref) for ref in sorted_refs],
            "currentTurn": self.current_turn,
            "changes": {
                "added": list(added),
            }
        }
    
    def get_generated_pending(self) -> list[str]:
        """Get all gen_* refs that are still pending (not yet saved)."""
        return [
            ref for ref in self.ref_to_uuid.keys()
            if ref.startswith("gen_") and self.ref_actions.get(ref) == "generated"
        ]
    
    # format_for_act_prompt() REMOVED (2026-01-16)
    # Was V5 approach showing refs+labels only. Replaced by build_act_entity_context()
    # in act.py which includes full entity data, saving re-read costs.

    # format_for_understand_prompt() REMOVED (2026-01-23)
    # Migrated to Context API: build_understand_context() in context/builders.py
    # Now includes both turn tracking table AND decision history in one place.

    # format_for_think_prompt() REMOVED (2026-01-23)
    # Migrated to Context API: build_think_context() in context/builders.py
    # Now uses ThinkContext.format_entity_context() with recipe detail tracking.

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
            # V7: Recipe detail tracking
            "ref_recipe_last_read_level": self.ref_recipe_last_read_level,
            "ref_recipe_last_full_turn": self.ref_recipe_last_full_turn,
            # V4 CONSOLIDATION: Temporal tracking
            "ref_turn_created": self.ref_turn_created,
            "ref_turn_last_ref": self.ref_turn_last_ref,
            "ref_source_step": self.ref_source_step,
            "ref_turn_promoted": self.ref_turn_promoted,
            "current_turn": self.current_turn,
            # V5: Understand context management
            "ref_active_reason": self.ref_active_reason,
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
        registry.ref_recipe_last_read_level = data.get("ref_recipe_last_read_level", {})
        registry.ref_recipe_last_full_turn = data.get("ref_recipe_last_full_turn", {})
        # V4 CONSOLIDATION: Temporal tracking
        registry.ref_turn_created = data.get("ref_turn_created", {})
        registry.ref_turn_last_ref = data.get("ref_turn_last_ref", {})
        registry.ref_source_step = data.get("ref_source_step", {})
        registry.ref_turn_promoted = data.get("ref_turn_promoted", {})
        registry.current_turn = data.get("current_turn", 0)
        # V5: Understand context management
        registry.ref_active_reason = data.get("ref_active_reason", {})
        return registry


# Backward compatibility alias (will be removed)
TurnIdRegistry = SessionIdRegistry
