# ID Translation Layer Specification

## Problem Statement

Act (and other LLM nodes) are exposed to raw UUIDs like `a508000d-9b55-40f0-8886-dbdd88bd2de2`. This causes:

1. **Typo risk** — LLMs can mistype long UUIDs
2. **Token waste** — 36 chars vs 8-10 chars per ID
3. **Cognitive load** — LLMs must track which UUID maps to which entity
4. **Reconstruction errors** — When shown truncated IDs (`..c69607bb`), LLMs invent the rest

**Observed failure (2026-01-06):**
```
Act saw: id:..c69607bb
Act tried: db_delete with id = "c69607bb-0000-0000-0000-000000000000"
Result: Delete failed (invalid UUID)
```

## Solution: System-Managed ID Translation

A translation layer sits between LLM nodes and CRUD operations. LLMs only ever see simplified refs like `recipe_1`, `inventory_12`, `task_3`.

```
┌─────────────────────────────────────────────────────────────┐
│                  LLM NODES (Act, Think, etc.)               │
│                                                             │
│  Only sees: recipe_1, recipe_2, inventory_5                 │
│  Never sees: a508000d-9b55-40f0-8886-dbdd88bd2de2          │
└─────────────────────────────────────────────────────────────┘
                            ↑ ↓
┌─────────────────────────────────────────────────────────────┐
│              ID TRANSLATION LAYER (TurnIdRegistry)          │
│                                                             │
│  translate_output(db_result) → replaces UUIDs with refs    │
│  translate_input(act_params) → replaces refs with UUIDs    │
└─────────────────────────────────────────────────────────────┘
                            ↑ ↓
┌─────────────────────────────────────────────────────────────┐
│                    CRUD LAYER (Supabase)                    │
│                                                             │
│  Only speaks UUIDs                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Ref Naming Convention

| Prefix | Meaning | Example |
|--------|---------|---------|
| `{type}_{n}` | Entity from database | `recipe_1`, `inventory_5` |
| `gen_{type}_{n}` | Generated this turn, not saved | `gen_recipe_1` |

**Counters reset each turn.** `recipe_1` in Turn 5 is different from `recipe_1` in Turn 6.

**Cross-turn references:** For entities referenced from prior turns, use same pattern. The system tracks the mapping.

---

## Core Operations

### 1. translate_output(db_result) → LLM-ready data

Called after every `db_read` operation.

**Input:** Raw DB result with UUIDs
```python
[
    {"id": "a508000d-9b55-40f0-8886-dbdd88bd2de2", "name": "Thai Curry", ...},
    {"id": "f527cc94-5af5-451d-9e4a-16fdb9582bdc", "name": "Cod Stir Fry", ...},
]
```

**Process:**
1. For each record, extract `id` field
2. Assign ref: `{table_singular}_{counter}` → `recipe_1`, `recipe_2`
3. Register mapping: `recipe_1 → a508000d-...`
4. Replace `id` field in record with ref

**Output:** Translated data for LLM
```python
[
    {"id": "recipe_1", "name": "Thai Curry", ...},
    {"id": "recipe_2", "name": "Cod Stir Fry", ...},
]
```

### 2. translate_input(params) → DB-ready params

Called before every `db_create`, `db_update`, `db_delete` operation.

**Input:** Act's params with refs
```python
{
    "table": "recipes",
    "filters": [{"field": "id", "op": "in", "value": ["recipe_1", "recipe_2"]}]
}
```

**Process:**
1. Walk all filter values looking for refs
2. Look up real UUIDs from registry
3. Substitute

**Output:** DB-ready params
```python
{
    "table": "recipes",
    "filters": [{"field": "id", "op": "in", "value": ["a508000d-...", "f527cc94-..."]}]
}
```

### 3. register_created(ref, uuid)

Called after `db_create` returns new IDs.

**Purpose:** Track generated entities that are now saved.

```python
# Act created with ref gen_recipe_1
# DB returned UUID abc123...
registry.register_created("gen_recipe_1", "abc123...")
# Now gen_recipe_1 → abc123... is in the mapping
# Future refs to gen_recipe_1 will resolve correctly
```

---

## Implementation: TurnIdRegistry

```python
@dataclass
class TurnIdRegistry:
    """
    Central registry for ID translation within a turn.
    
    All CRUD operations flow through this layer.
    LLMs never see UUIDs.
    """
    
    turn_id: str
    
    # ref → UUID mapping
    ref_to_uuid: dict[str, str] = field(default_factory=dict)
    
    # UUID → ref mapping (for lookups)
    uuid_to_ref: dict[str, str] = field(default_factory=dict)
    
    # Counters per entity type
    counters: dict[str, int] = field(default_factory=dict)
    
    def _next_ref(self, entity_type: str, prefix: str = "") -> str:
        """Generate next ref for an entity type."""
        self.counters[entity_type] = self.counters.get(entity_type, 0) + 1
        return f"{prefix}{entity_type}_{self.counters[entity_type]}"
    
    # =========================================================================
    # Output Translation (DB → LLM)
    # =========================================================================
    
    def translate_read_output(
        self, 
        records: list[dict], 
        table: str,
    ) -> list[dict]:
        """
        Translate DB read results for LLM consumption.
        
        Replaces UUID id fields with simple refs.
        """
        entity_type = self._table_to_type(table)
        translated = []
        
        for record in records:
            new_record = record.copy()
            
            if "id" in record:
                uuid = record["id"]
                
                # Check if we already have a ref for this UUID
                if uuid in self.uuid_to_ref:
                    ref = self.uuid_to_ref[uuid]
                else:
                    # Assign new ref
                    ref = self._next_ref(entity_type)
                    self.ref_to_uuid[ref] = uuid
                    self.uuid_to_ref[uuid] = ref
                
                new_record["id"] = ref
            
            # Also translate FK fields
            for fk_field in self._get_fk_fields(table):
                if fk_field in record and record[fk_field]:
                    fk_uuid = record[fk_field]
                    if fk_uuid in self.uuid_to_ref:
                        new_record[fk_field] = self.uuid_to_ref[fk_uuid]
            
            translated.append(new_record)
        
        return translated
    
    def translate_create_output(
        self,
        created_ids: list[str],
        table: str,
        original_refs: list[str] | None = None,
    ) -> list[str]:
        """
        Register created entities and return their refs.
        
        If original_refs provided (from gen_* refs), updates those mappings.
        Otherwise assigns new refs.
        """
        entity_type = self._table_to_type(table)
        result_refs = []
        
        for i, uuid in enumerate(created_ids):
            if original_refs and i < len(original_refs):
                # Update existing gen_* ref to point to real UUID
                ref = original_refs[i]
                self.ref_to_uuid[ref] = uuid
                self.uuid_to_ref[uuid] = ref
                
                # Also create a saved ref alias
                saved_ref = self._next_ref(entity_type)
                self.ref_to_uuid[saved_ref] = uuid
                # Don't overwrite uuid_to_ref - keep original gen_* ref
                
                result_refs.append(ref)
            else:
                # New entity, assign ref
                ref = self._next_ref(entity_type)
                self.ref_to_uuid[ref] = uuid
                self.uuid_to_ref[uuid] = ref
                result_refs.append(ref)
        
        return result_refs
    
    # =========================================================================
    # Input Translation (LLM → DB)
    # =========================================================================
    
    def translate_filters(self, filters: list[dict]) -> list[dict]:
        """
        Translate filter values from refs to UUIDs.
        """
        translated = []
        
        for f in filters:
            new_filter = f.copy()
            value = f.get("value")
            
            if isinstance(value, str) and self._is_ref(value):
                uuid = self.ref_to_uuid.get(value)
                if uuid:
                    new_filter["value"] = uuid
            elif isinstance(value, list):
                new_filter["value"] = [
                    self.ref_to_uuid.get(v, v) if self._is_ref(v) else v
                    for v in value
                ]
            
            translated.append(new_filter)
        
        return translated
    
    def translate_payload(self, data: dict, table: str) -> dict:
        """
        Translate FK fields in create/update payload from refs to UUIDs.
        """
        translated = data.copy()
        
        for fk_field in self._get_fk_fields(table):
            if fk_field in translated:
                value = translated[fk_field]
                if isinstance(value, str) and self._is_ref(value):
                    uuid = self.ref_to_uuid.get(value)
                    if uuid:
                        translated[fk_field] = uuid
        
        return translated
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def _is_ref(self, value: str) -> bool:
        """Check if a value is a ref (not a UUID)."""
        # UUIDs have dashes and are 36 chars
        if "-" in value and len(value) == 36:
            return False
        # Refs match pattern: {type}_{n} or gen_{type}_{n}
        return "_" in value and not value.startswith("-")
    
    def _table_to_type(self, table: str) -> str:
        """Convert table name to entity type (singular)."""
        mapping = {
            "recipes": "recipe",
            "recipe_ingredients": "ingredient",
            "inventory": "inventory",
            "shopping_list": "shopping",
            "meal_plans": "meal",
            "tasks": "task",
            "preferences": "pref",
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
    
    def get_uuid(self, ref: str) -> str | None:
        """Look up UUID for a ref."""
        return self.ref_to_uuid.get(ref)
    
    def get_ref(self, uuid: str) -> str | None:
        """Look up ref for a UUID."""
        return self.uuid_to_ref.get(uuid)
    
    def format_for_prompt(self) -> str:
        """Format current mappings for debugging/display."""
        if not self.ref_to_uuid:
            return "*No entities registered.*"
        
        lines = ["| Ref | Entity |"]
        lines.append("|-----|--------|")
        
        for ref in sorted(self.ref_to_uuid.keys()):
            # Don't show UUID, just the ref
            lines.append(f"| {ref} | ✓ |")
        
        return "\n".join(lines)
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "ref_to_uuid": self.ref_to_uuid,
            "uuid_to_ref": self.uuid_to_ref,
            "counters": self.counters,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TurnIdRegistry":
        registry = cls(turn_id=data.get("turn_id", ""))
        registry.ref_to_uuid = data.get("ref_to_uuid", {})
        registry.uuid_to_ref = data.get("uuid_to_ref", {})
        registry.counters = data.get("counters", {})
        return registry
```

---

## Integration Points

### 1. CRUD Layer (`src/alfred/crud/operations.py`)

Wrap all CRUD operations:

```python
async def db_read(table: str, filters: list, ..., registry: TurnIdRegistry) -> list[dict]:
    # Translate filters (in case they reference prior entities)
    translated_filters = registry.translate_filters(filters)
    
    # Execute query
    result = await _raw_db_read(table, translated_filters, ...)
    
    # Translate output
    return registry.translate_read_output(result, table)


async def db_create(table: str, data: dict | list, ..., registry: TurnIdRegistry) -> list[str]:
    # Translate FK fields in payload
    if isinstance(data, list):
        translated_data = [registry.translate_payload(d, table) for d in data]
    else:
        translated_data = registry.translate_payload(data, table)
    
    # Execute create
    created_uuids = await _raw_db_create(table, translated_data, ...)
    
    # Register and return refs
    return registry.translate_create_output(created_uuids, table)


async def db_delete(table: str, filters: list, ..., registry: TurnIdRegistry) -> int:
    # Translate filters
    translated_filters = registry.translate_filters(filters)
    
    # Execute delete
    return await _raw_db_delete(table, translated_filters, ...)
```

### 2. Act Node (`src/alfred/graph/nodes/act.py`)

Initialize registry at start of turn, pass to CRUD:

```python
async def act_node(state: AlfredState) -> dict:
    # Get or create registry for this turn
    registry_data = state.get("id_registry")
    if registry_data:
        registry = TurnIdRegistry.from_dict(registry_data)
    else:
        registry = TurnIdRegistry(turn_id=state.get("turn_id", ""))
    
    # ... execute step ...
    
    # CRUD calls use registry
    result = await db_read(table, filters, registry=registry)
    
    # ... format result for LLM (already has refs, not UUIDs) ...
    
    return {
        "id_registry": registry.to_dict(),
        # ...
    }
```

### 3. Step Result Formatting (`_format_step_results`)

**Remove all ID truncation.** IDs are already simple refs:

```python
# OLD (broken):
id_short = entity.id[-8:]  # Truncating UUID

# NEW (correct):
id_display = entity.id  # Already a ref like "recipe_1"
```

---

## Prompt Updates Required

### Act Prompts

**Remove:**
- All UUID examples
- References to "copy UUID from..."
- ID truncation explanations
- Instructions about reconstructing IDs

**Add:**
- "IDs are simple refs like `recipe_1`, `inventory_5`"
- "Use IDs exactly as shown"
- "Never construct or modify IDs"

### Think Prompts

**Remove:**
- UUID references in examples

**Update:**
- Examples to use `recipe_1` format

### Reply Prompts

**No UUID exposure** — Reply should use entity names, not IDs.

---

## Hygiene Audit Checklist

Search codebase for:

| Pattern | Should Be | Location |
|---------|-----------|----------|
| `id[-8:]` | Removed | `act.py`, `injection.py` |
| `..abc123` | Removed | Prompt files |
| `uuid-here` | Changed to `recipe_1` | Prompt examples |
| `a508000d-` | Removed | All files |
| `36 char` | Removed | Comments |

---

## Migration Steps

### Phase 1: Core Layer
1. Create `TurnIdRegistry` class
2. Wrap CRUD operations with translation
3. Update `act_node` to use registry

### Phase 2: Prompt Cleanup
1. Update `prompts/act/*.md` — remove UUID refs
2. Update `prompts/think.md` — simplify ID examples
3. Update `prompts/understand.md` — use ref format
4. Update `prompts/reply.md` — no ID exposure

### Phase 3: Code Cleanup
1. Remove `id[-8:]` truncation
2. Remove `_format_entity_refs` UUID handling
3. Update `_format_step_results` for refs
4. Remove old `TurnIdMapper` (superseded by `TurnIdRegistry`)

---

## Testing

### Scenario 1: Read → Delete
```
User: "delete all my recipes"
Step 1: Read recipes → [recipe_1, recipe_2, recipe_3]
Step 2: Delete where id in [recipe_1, recipe_2, recipe_3]
System: Translates to real UUIDs, executes delete
```

### Scenario 2: Generate → Save
```
Step 1: Generate 2 recipes → [gen_recipe_1, gen_recipe_2]
Step 2: Save recipes → System creates, returns [recipe_1, recipe_2]
Step 3: Save ingredients with recipe_id = recipe_1, recipe_2
System: Translates to real UUIDs
```

### Scenario 3: Read → Update
```
Step 1: Read inventory → [inventory_1, inventory_2]
Step 2: Update inventory_1 quantity to 5
System: Translates inventory_1 to real UUID
```

---

## Success Criteria

1. **Zero UUIDs in LLM prompts** — grep for UUID patterns returns nothing
2. **All CRUD through registry** — no direct DB access bypassing translation
3. **Consistent ref format** — `{type}_{n}` everywhere
4. **Delete/update works** — operations with refs execute correctly
