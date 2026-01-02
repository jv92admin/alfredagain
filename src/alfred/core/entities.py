"""
Alfred V3 - Entity Lifecycle Framework.

Entities are tracked objects (recipes, meal plans, tasks, etc.) that flow through the system.

3-State Model:
- PENDING: Generated content awaiting user confirmation
- ACTIVE: User confirmed or from database (working with)
- INACTIVE: Rejected, replaced, or stale (garbage collected)

Ownership Rules:
- Act creates entities (tags them pending/active at creation)
- Understand modifies states (confirmation/rejection signals)
- Summarize deletes entities (garbage collection)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


class EntityState(Enum):
    """Entity lifecycle states."""
    
    PENDING = "pending"    # Generated, awaiting confirmation
    ACTIVE = "active"      # User confirmed or working with
    INACTIVE = "inactive"  # Rejected, replaced, or stale


@dataclass
class Entity:
    """
    A tracked entity in the system.
    
    Entities are created by Act steps and tracked across turns.
    """
    
    id: str                    # UUID or temp_id (e.g., "temp_recipe_1")
    type: str                  # "recipe", "meal_plan", "task", "ingredient", etc.
    label: str                 # Human-readable (e.g., "Butter Chicken")
    state: EntityState         # Current lifecycle state
    source: str                # "db_read", "generate", "user_input"
    turn_created: int          # Turn number when created
    turn_last_ref: int = 0     # Turn number when last referenced (for GC)
    
    # Optional metadata
    subdomain: str | None = None  # "recipes", "meal_plans", etc.
    data: dict | None = None      # Snapshot of entity data (optional, for pending entities)
    
    def to_ref(self) -> dict:
        """Convert to lightweight reference for prompt injection."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "state": self.state.value,
        }
    
    def to_dict(self) -> dict:
        """Full serialization for state storage."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "state": self.state.value,
            "source": self.source,
            "turn_created": self.turn_created,
            "turn_last_ref": self.turn_last_ref,
            "subdomain": self.subdomain,
            "data": self.data,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        """Deserialize from dict."""
        return cls(
            id=data["id"],
            type=data["type"],
            label=data["label"],
            state=EntityState(data["state"]),
            source=data["source"],
            turn_created=data["turn_created"],
            turn_last_ref=data.get("turn_last_ref", 0),
            subdomain=data.get("subdomain"),
            data=data.get("data"),
        )


@dataclass
class EntityRegistry:
    """
    Manages the lifecycle of all entities in a conversation.
    
    Provides:
    - State transitions (pending → active, active → inactive)
    - Filtered access (get_active, get_pending)
    - Garbage collection (remove stale inactive entities)
    """
    
    entities: dict[str, Entity] = field(default_factory=dict)
    
    # Garbage collection thresholds
    INACTIVE_TTL_TURNS: int = 2      # Remove inactive entities after N turns
    UNREFERENCED_TTL_TURNS: int = 5  # Mark unreferenced entities inactive after N turns
    PENDING_TTL_TURNS: int = 3       # Mark unconfirmed pending entities inactive after N turns
    
    # Context limits (for prompt injection)
    MAX_ENTITIES_PER_TYPE: int = 5   # Limit entities per type in prompts
    
    def add(self, entity: Entity) -> None:
        """Add a new entity to the registry."""
        self.entities[entity.id] = entity
    
    def get(self, entity_id: str) -> Entity | None:
        """Get entity by ID."""
        return self.entities.get(entity_id)
    
    def update_state(self, entity_id: str, new_state: EntityState) -> bool:
        """
        Update an entity's state.
        
        Returns True if entity was found and updated.
        """
        entity = self.entities.get(entity_id)
        if entity:
            entity.state = new_state
            return True
        return False
    
    def touch(self, entity_id: str, current_turn: int) -> bool:
        """
        Mark an entity as referenced in the current turn.
        
        Updates turn_last_ref to prevent garbage collection.
        Returns True if entity was found.
        """
        entity = self.entities.get(entity_id)
        if entity:
            entity.turn_last_ref = current_turn
            return True
        return False
    
    def get_active(self) -> list[Entity]:
        """Get all entities with ACTIVE state."""
        return [e for e in self.entities.values() if e.state == EntityState.ACTIVE]
    
    def get_pending(self) -> list[Entity]:
        """Get all entities with PENDING state."""
        return [e for e in self.entities.values() if e.state == EntityState.PENDING]
    
    def get_by_type(self, entity_type: str) -> list[Entity]:
        """Get all entities of a specific type."""
        return [e for e in self.entities.values() if e.type == entity_type]
    
    def get_active_refs(self) -> list[dict]:
        """Get lightweight references for all active entities."""
        return [e.to_ref() for e in self.get_active()]
    
    def get_pending_refs(self) -> list[dict]:
        """Get lightweight references for all pending entities."""
        return [e.to_ref() for e in self.get_pending()]
    
    def get_counts_by_type(self) -> dict[str, int]:
        """Get counts of active entities by type (for Think context)."""
        counts: dict[str, int] = {}
        for entity in self.get_active():
            counts[entity.type] = counts.get(entity.type, 0) + 1
        return counts
    
    def get_recent_by_type(self, state_filter: EntityState | None = None) -> dict[str, list[Entity]]:
        """
        Get entities grouped by type, sorted by recency, limited per type.
        
        This is the primary method for prompt injection - prevents context pollution.
        
        Args:
            state_filter: Only include entities with this state. None = all states.
            
        Returns:
            Dict mapping entity type to list of most recent entities (limited by MAX_ENTITIES_PER_TYPE).
        """
        # Group by type
        by_type: dict[str, list[Entity]] = {}
        for entity in self.entities.values():
            if state_filter is not None and entity.state != state_filter:
                continue
            if entity.type not in by_type:
                by_type[entity.type] = []
            by_type[entity.type].append(entity)
        
        # Sort each type by recency (most recently referenced first, then most recently created)
        for entity_type, entities in by_type.items():
            entities.sort(key=lambda e: (e.turn_last_ref, e.turn_created), reverse=True)
            # Limit per type
            by_type[entity_type] = entities[:self.MAX_ENTITIES_PER_TYPE]
        
        return by_type
    
    def get_for_prompt(self, include_pending: bool = True) -> dict[str, list[dict]]:
        """
        Get organized entity refs for prompt injection.
        
        Returns a dict with 'active' and optionally 'pending' sections,
        each containing entities grouped by type.
        
        This is the main method for building entity context in prompts.
        """
        result: dict[str, list[dict]] = {}
        
        # Get active entities by type (most recent first, limited)
        active_by_type = self.get_recent_by_type(EntityState.ACTIVE)
        active_refs = []
        for entity_type, entities in sorted(active_by_type.items()):
            for entity in entities:
                active_refs.append(entity.to_ref())
        result["active"] = active_refs
        
        # Optionally include pending
        if include_pending:
            pending_by_type = self.get_recent_by_type(EntityState.PENDING)
            pending_refs = []
            for entity_type, entities in sorted(pending_by_type.items()):
                for entity in entities:
                    pending_refs.append(entity.to_ref())
            result["pending"] = pending_refs
        
        return result
    
    def garbage_collect(self, current_turn: int) -> list[str]:
        """
        Remove stale entities based on TTL rules.
        
        Rules:
        1. INACTIVE entities older than INACTIVE_TTL_TURNS are removed
        2. ACTIVE entities not referenced in UNREFERENCED_TTL_TURNS are marked INACTIVE
        3. PENDING entities not confirmed in PENDING_TTL_TURNS are marked INACTIVE
        
        Returns list of removed entity IDs.
        """
        removed: list[str] = []
        to_mark_inactive: list[str] = []
        
        for entity_id, entity in list(self.entities.items()):
            turns_since_ref = current_turn - entity.turn_last_ref
            turns_since_create = current_turn - entity.turn_created
            
            # Rule 1: Remove old inactive entities
            if entity.state == EntityState.INACTIVE:
                if turns_since_ref >= self.INACTIVE_TTL_TURNS:
                    removed.append(entity_id)
            
            # Rule 2: Mark unreferenced active entities as inactive
            elif entity.state == EntityState.ACTIVE:
                if turns_since_ref >= self.UNREFERENCED_TTL_TURNS:
                    to_mark_inactive.append(entity_id)
            
            # Rule 3: Mark old unconfirmed pending entities as inactive
            elif entity.state == EntityState.PENDING:
                if turns_since_create >= self.PENDING_TTL_TURNS:
                    to_mark_inactive.append(entity_id)
        
        # Apply state transitions
        for entity_id in to_mark_inactive:
            self.update_state(entity_id, EntityState.INACTIVE)
        
        # Remove garbage
        for entity_id in removed:
            del self.entities[entity_id]
        
        return removed
    
    def merge_from_turn(self, turn_entities: list[Entity]) -> None:
        """
        Merge entities created during a turn into the registry.
        
        Called by Summarize at end of turn.
        """
        for entity in turn_entities:
            self.add(entity)
    
    def apply_updates(self, updates: list[dict]) -> list[str]:
        """
        Apply batch state updates from Understand.
        
        updates: [{"id": "x", "new_state": "active"}, ...]
        
        Returns list of entity IDs that were updated.
        """
        updated: list[str] = []
        for update in updates:
            entity_id = update.get("id")
            new_state_str = update.get("new_state")
            if entity_id and new_state_str:
                try:
                    new_state = EntityState(new_state_str)
                    if self.update_state(entity_id, new_state):
                        updated.append(entity_id)
                except ValueError:
                    pass  # Invalid state string, skip
        return updated
    
    def __len__(self) -> int:
        return len(self.entities)
    
    def __iter__(self) -> Iterator[Entity]:
        return iter(self.entities.values())
    
    def to_dict(self) -> dict:
        """Serialize registry for state storage."""
        return {
            "entities": {k: v.to_dict() for k, v in self.entities.items()}
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EntityRegistry":
        """Deserialize from dict."""
        registry = cls()
        entities_data = data.get("entities", {})
        for entity_id, entity_data in entities_data.items():
            registry.entities[entity_id] = Entity.from_dict(entity_data)
        return registry

