# Session ID Registry — Proper Implementation Spec

## Problem Statement

The current ID system (`TurnIdRegistry`) resets every turn, breaking cross-turn operations like "delete those recipes I just listed."

Additionally, the current architecture asks the **LLM to extract/resolve IDs** in Understand, which is:
1. Error-prone (LLMs hallucinate or misformat IDs)
2. Unnecessary (IDs should be deterministically mapped by the system)
3. Confusing (mixing probabilistic entity resolution with deterministic ID lookup)

## The Correct Architecture

### Separation of Concerns

```
┌─────────────────────────────────────────────────────────────────┐
│         SESSION ID REGISTRY (System Layer, Deterministic)       │
│                                                                 │
│  - Assigned by SYSTEM when db_read/db_create returns data      │
│  - Persists across turns in state                              │
│  - Pure lookup: recipe_1 → abc123-uuid                         │
│  - NO LLM involvement                                          │
│                                                                 │
│  recipe_1 → abc123...    (db_read turn 1)                      │
│  recipe_2 → def456...    (db_read turn 1)                      │
│  gen_recipe_1 → (pending) (generate turn 2)                    │
│  recipe_3 → ghi789...    (db_create turn 2)                    │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│         UNDERSTAND (LLM Layer, Probabilistic)                   │
│                                                                 │
│  - Context curation: what entities are relevant?               │
│  - Reference resolution: "that recipe" → recipe_1 (from ctx)   │
│  - Constraint extraction                                       │
│  - Quick mode detection                                        │
│                                                                 │
│  Does NOT: Look up UUIDs, extract IDs from scratch             │
│  Does: Confirm which simple ref the user means                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
TURN 1: "what recipes do i have?"

  db_read("recipes") returns:
    [{id: "abc123-...", name: "Thai Curry"}, {id: "def456-...", name: "Pasta"}]
                                    ↓
  SYSTEM (in CRUD layer) intercepts output:
    - Assigns: recipe_1 → abc123, recipe_2 → def456
    - Replaces IDs in data
    - Persists mapping in state.session_id_registry
                                    ↓
  LLM sees:
    [{id: "recipe_1", name: "Thai Curry"}, {id: "recipe_2", name: "Pasta"}]
                                    ↓
  Reply: "You have Thai Curry (recipe_1) and Pasta (recipe_2)"


TURN 2: "delete all of them"

  Understand:
    - Sees "all of them" in user message
    - Sees recipe_1, recipe_2 in Entity Context (from prior turn)
    - Outputs: referenced_entities: ["recipe_1", "recipe_2"]
    - NO UUID lookup needed
                                    ↓
  Think:
    - Plans: delete recipe_1, recipe_2
                                    ↓
  Act:
    - Calls db_delete with filter: id in ["recipe_1", "recipe_2"]
                                    ↓
  SYSTEM (in CRUD layer) intercepts input:
    - Looks up: recipe_1 → abc123, recipe_2 → def456
    - Translates filter to real UUIDs
    - Executes delete
```

### Generate Flow

```
TURN: "create a simple cod recipe"

  Generate step produces:
    {name: "Simple Cod", ingredients: [...]}
                                    ↓
  SYSTEM (post-generate):
    - Assigns: gen_recipe_1 → (pending, no UUID yet)
    - Stores content with ref
                                    ↓
  LLM sees in subsequent steps:
    gen_recipe_1: "Simple Cod" (pending)
                                    ↓
  Write step:
    - Act calls db_create with gen_recipe_1's content
                                    ↓
  SYSTEM (post-create):
    - Receives UUID xyz789 from DB
    - Updates: gen_recipe_1 → xyz789
    - Optionally assigns: recipe_3 → xyz789 (saved alias)
```

---

## What Exists Now (To Deprecate/Refactor)

### Files to Modify

| File | Current State | Action |
|------|---------------|--------|
| `src/alfred/core/id_registry.py` | TurnIdRegistry resets each turn | Rename to `SessionIdRegistry`, persist across turns |
| `src/alfred/core/id_mapper.py` | Legacy gen_* → UUID mapper | Merge into SessionIdRegistry or deprecate |
| `src/alfred/tools/crud.py` | Has translation layer (correct) | Keep, ensure uses session registry |
| `src/alfred/graph/nodes/act.py` | Initializes TurnIdRegistry | Use session registry from state |
| `src/alfred/graph/nodes/understand.py` | Tries to populate registry from entity_context | Remove this; registry already has mappings |
| `src/alfred/graph/state.py` | Has `id_registry: dict` field | Rename to `session_id_registry` |

### Prompts to Update

| Prompt | Current State | Action |
|--------|---------------|--------|
| `prompts/understand.md` | Asks LLM to output `resolved_id` UUIDs | Remove ID extraction; just reference resolution to simple refs |
| `prompts/act/base.md` | Already mentions simple refs | Verify consistent |
| `prompts/act/generate.md` | Doesn't exist yet | Create; tell LLM to use gen_* refs for created content |
| `prompts/think.md` | Uses referenced_entities | Ensure expects simple refs |

### Concepts to Remove

1. **LLM-based ID extraction** - Understand should NOT output UUIDs
2. **Turn-scoped registry reset** - Registry persists across turns
3. **Registry population from entity_context** - Registry IS the source of truth

---

## Implementation Status

### Phase 1: Core Registry Refactor ✅

- [x] **Rename `TurnIdRegistry` → `SessionIdRegistry`**
  - File: `src/alfred/core/id_registry.py`
  - Session-scoped, persists across turns

- [x] **Update state to persist registry across turns**
  - File: `src/alfred/graph/state.py`
  - Field: `session_id_registry: dict | None`

- [x] **Remove registry reset logic**
  - File: `src/alfred/graph/nodes/act.py`
  - Uses existing registry from state if present

- [x] **Remove registry population from entity_context**
  - File: `src/alfred/graph/nodes/understand.py`
  - Registry is populated by CRUD layer only

### Phase 2: CRUD Integration ✅

- [x] **db_read populates registry**
  - `translate_read_output` assigns refs and persists

- [x] **db_create updates registry**
  - gen_* refs → real UUIDs after insert

- [x] **db_delete/update translates refs**
  - Filter values translated before execution

### Phase 3: Generate Step Handling ✅

- [x] **Updated generate.md prompt**
  - LLM outputs content, system assigns `gen_*` refs

- [x] **Post-generate ref assignment**
  - System assigns refs after generate step completes

### Phase 4: Understand Prompt Cleanup ✅

- [x] **Removed ID extraction from Understand prompt**
  - Changed `resolved_id` → `resolved_ref`
  - All examples use simple refs (recipe_1, not UUIDs)

- [x] **Updated output model**
  - `referenced_entities` contains simple refs

### Phase 5: Deprecation ✅

- [x] **id_mapper.py deprecated**
  - Added deprecation notice
  - Kept for backward compat during migration

- [x] **All prompts updated**
  - No UUID references in any prompt
  - All examples use simple refs

### Phase 6: Testing (Manual)

- [ ] **Test: Read → Delete flow**
  - Turn 1: Read recipes (assigns recipe_1, recipe_2)
  - Turn 2: Delete recipe_1, recipe_2 (uses persisted mappings)

- [ ] **Test: Generate → Save flow**
  - Turn 1: Generate recipe (assigns gen_recipe_1)
  - Turn 1: Save gen_recipe_1 (maps to real UUID)

- [ ] **Test: Multi-turn reference**
  - Turn 1: List recipes
  - Turn 2: Add one to meal plan
  - Turn 3: Delete the meal plan

---

## Success Criteria

1. **No UUIDs in LLM context** - grep for UUID patterns returns nothing in prompt logs
2. **Cross-turn operations work** - "delete those recipes" works after listing them
3. **100% deterministic ID translation** - No LLM inference for ID mapping
4. **Understand focuses on context curation** - Not ID extraction
5. **Generate refs work** - gen_recipe_1 persists through save

---

## Migration Notes

- Existing conversations with old-format IDs may break
- Consider: Clear session_id_registry on major version bump
- Entity context still useful for: labels, types, tiering (not ID storage)
