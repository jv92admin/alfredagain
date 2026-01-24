# Session ID Registry — Implementation Spec

## Overview

The `SessionIdRegistry` is Alfred's single source of truth for entity ID management. It ensures:
1. LLMs never see UUIDs (only simple refs like `recipe_1`)
2. ID mappings persist across turns
3. FK references are automatically handled (lazy registration + enrichment)

---

## Architecture

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
│         UNDERSTAND (LLM Layer — Memory Manager)                 │
│                                                                 │
│  - Context curation: what entities are relevant?               │
│  - Reference resolution: "that recipe" → recipe_1 (from ctx)   │
│  - Long-term retention decisions                               │
│  - Quick mode detection                                        │
│                                                                 │
│  Does NOT: Look up UUIDs, rewrite messages, give instructions  │
│  Does: Curate context, resolve references, explain retention   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Read Flow

```
TURN 1: "what recipes do i have?"

  db_read("recipes") returns:
    [{id: "abc123-...", name: "Thai Curry"}, {id: "def456-...", name: "Pasta"}]
                                    ↓
  SYSTEM (in CRUD layer) intercepts output:
    - Assigns: recipe_1 → abc123, recipe_2 → def456
    - Sets labels: recipe_1 → "Thai Curry"
    - Persists mapping in state.id_registry
                                    ↓
  LLM sees:
    [{id: "recipe_1", name: "Thai Curry"}, {id: "recipe_2", name: "Pasta"}]
                                    ↓
  Reply: "You have Thai Curry (recipe_1) and Pasta (recipe_2)"
```

### Cross-Turn Reference Flow

```
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
    - Stores content in pending_artifacts
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
    - Clears pending_artifacts[gen_recipe_1]
```

### ✅ DONE: Smart Read Rerouting for gen_* Refs (V8)

**Implemented in `crud.py` → `_try_reroute_pending_read()`**

**Behavior:**
- Think plans `read gen_recipe_1` → CRUD layer detects pending ref → returns from `pending_artifacts`
- Uniform mental model: "need data? read it" (works for both DB and generated content)

**Implementation:**
- Added `_try_reroute_pending_read()` function in `crud.py`
- Detects when filter references a gen_* ref with `__pending__` UUID
- Returns artifact from `pending_artifacts` formatted to match db_read shape
- Handles both single ref (`=` operator) and multiple refs (`in` operator)

**Benefits achieved:**
- `gen_*` refs can be read like any other entity
- Removed "don't read gen_*" rules from prompts
- Generated content can "fade" from Active Entities and still be retrievable

### FK Lazy Registration Flow (V5)

```
TURN: "what's in my meal plan?"

  db_read("meal_plans") returns:
    [{id: "meal-uuid-1", date: "2026-01-12", recipe_id: "recipe-uuid-xyz"}]
                                    ↓
  SYSTEM (translate_read_output):
    - Assigns: meal_1 → meal-uuid-1
    - recipe_id "recipe-uuid-xyz" not in registry → LAZY REGISTER
    - Assigns: recipe_1 → recipe-uuid-xyz (action: "linked")
    - Queues for enrichment: recipe_1 → ("recipes", "name")
                                    ↓
  SYSTEM (_enrich_lazy_registrations):
    - Batch queries: SELECT id, name FROM recipes WHERE id IN (...)
    - Updates label: recipe_1 → "Butter Chicken"
                                    ↓
  SYSTEM (_add_enriched_labels):
    - Adds _recipe_id_label: "Butter Chicken" to result
                                    ↓
  LLM sees:
    [{id: "meal_1", date: "2026-01-12", recipe_id: "recipe_1", 
      _recipe_id_label: "Butter Chicken"}]
                                    ↓
  Display: "2026-01-12 [lunch] → Butter Chicken (recipe_1) id:meal_1"
```

---

## Registry Fields

### Core ID Mapping
```python
ref_to_uuid: dict[str, str]      # recipe_1 → abc123-uuid
uuid_to_ref: dict[str, str]      # abc123-uuid → recipe_1
counters: dict[str, int]         # recipe → 3 (next ref will be recipe_4)
gen_counters: dict[str, int]     # recipe → 1 (next gen ref will be gen_recipe_2)
```

### Entity Metadata
```python
ref_actions: dict[str, str]      # recipe_1 → "read" | "created" | "linked" | etc.
ref_labels: dict[str, str]       # recipe_1 → "Butter Chicken"
ref_types: dict[str, str]        # recipe_1 → "recipe"
```

### Temporal Tracking
```python
ref_turn_created: dict[str, int]   # recipe_1 → 3 (first seen in turn 3)
ref_turn_last_ref: dict[str, int]  # recipe_1 → 5 (last referenced in turn 5)
ref_source_step: dict[str, int]    # gen_recipe_1 → 2 (created in step 2)
current_turn: int                  # Current turn number
```

### Generated Content
```python
pending_artifacts: dict[str, dict]  # gen_recipe_1 → {full JSON content}
```

### V9: Unified Data Access
```python
# Single source of truth for "does this entity have data available?"
get_entity_data(ref: str) -> dict | None

# Unified modification API for gen_* artifacts
update_entity_data(ref: str, content: dict) -> bool
```

### V5: Context Curation
```python
ref_active_reason: dict[str, str]        # gen_meal_plan_1 → "User's ongoing goal"
_lazy_enrich_queue: dict[str, tuple]     # Transient: refs needing name enrichment
```

---

## Key Methods

### Registration
- `_next_ref(entity_type)` → Generate next ref (recipe_1, recipe_2, ...)
- `_next_gen_ref(entity_type)` → Generate next gen ref (gen_recipe_1, ...)
- `register_generated(entity_type, label, content)` → Register pending artifact
- `register_created(gen_ref, uuid, entity_type, label)` → Promote gen ref or create new

### Translation
- `translate_read_output(records, table)` → UUIDs → refs, lazy register FKs
- `translate_filters(filters)` → refs → UUIDs for queries
- `translate_payload(data, table)` → refs → UUIDs for create/update

### Enrichment (V5)
- `get_lazy_enrich_queue()` → Get refs needing name lookup
- `apply_enrichment(enrichments)` → Update labels from batch query
- `_compute_entity_label(record, entity_type)` → Type-specific label computation

### View Methods
- `format_for_think_prompt()` → Delineated: Pending → Recent → Long Term
- `format_for_understand_prompt()` → Full context with turn annotations
- `get_active_entities(turns_window)` → Returns (recent, retained) tuple

**Note:** Act's entity context is built by `_build_enhanced_entity_context()` in `act.py`, not by the registry.

### V7: Artifact Promotion Tracking
- `ref_turn_promoted` → Track which turn an artifact was promoted (gen_ref → UUID)
- `get_just_promoted_artifacts()` → Artifacts promoted this turn (for linked tables)
- `clear_turn_promoted_artifacts()` → Clear at turn end (called by Summarize)

### V9: Unified Data Access
- `get_entity_data(ref)` → **Single source of truth** for entity data. Returns content from `pending_artifacts` or `None`
- `update_entity_data(ref, content)` → Unified modification for gen_* artifacts. Updates content + label

**Key principle:** These methods work identically for all refs. The registry determines what data it has available — callers don't need `startswith("gen_")` checks.

### Serialization
- `to_dict()` → Serialize for state storage
- `from_dict(data)` → Deserialize from state

---

## Integration with Context API (V7 → V9)

The registry is consumed by the **Context API** (`src/alfred/context/`):

```python
# Context API uses registry for Layer 1 (Entity Context)
from alfred.context.entity import get_entity_context

ctx = get_entity_context(registry, mode="refs_and_labels")
# Returns: EntityContext with active, generated, retained lists
```

### V9: Unified View Across Nodes

All nodes now have access to generated content (`pending_artifacts`):

| Node | What It Sees |
|------|--------------|
| **Think** | Refs + labels (via ThinkContext) |
| **Act** | Full JSON injection for write/generate/analyze steps |
| **Reply** | Full JSON (via ReplyContext.pending_artifacts) ← **NEW in V9** |

This enables Reply to display generated recipes/meal plans when users ask "show me that recipe".

**Important:** The registry stores refs + labels for regular entities, and full content for generated entities in `pending_artifacts`.
See `docs/context-engineering-architecture.md` for the "refs vs content" gap.

---

## Implementation Status

### All Phases Complete ✅

| Phase | Status |
|-------|--------|
| Core Registry Refactor | ✅ Complete |
| CRUD Integration | ✅ Complete |
| Generate Step Handling | ✅ Complete |
| Understand Prompt Cleanup | ✅ Complete |
| Deprecation | ✅ Complete |
| V5 Context Curation | ✅ Complete |
| V5 FK Enrichment | ✅ Complete |

### Testing Status

| Test | Status |
|------|--------|
| Read → Delete flow | ✅ Working |
| Generate → Save flow | ✅ Working |
| Multi-turn reference | ✅ Working |
| FK lazy registration | ✅ Working |
| Name enrichment | ✅ Working |

---

## Success Criteria ✅

1. **No UUIDs in LLM context** ✅ — All prompts use simple refs
2. **Cross-turn operations work** ✅ — Registry persists via conversation state
3. **100% deterministic ID translation** ✅ — No LLM inference for ID mapping
4. **Understand focuses on context curation** ✅ — Memory Manager role
5. **Generate refs work** ✅ — gen_recipe_1 persists through save
6. **FK refs enriched** ✅ — Lazy-registered refs get real names

---

## Files

| File | Purpose |
|------|---------|
| `src/alfred/core/id_registry.py` | SessionIdRegistry implementation |
| `src/alfred/tools/crud.py` | CRUD layer with ID translation + enrichment |
| `src/alfred/graph/workflow.py` | Loads registry from conversation |
| `src/alfred/graph/nodes/summarize.py` | Persists registry to conversation |
| `src/alfred/prompts/injection.py` | Display formatting with labels |

---

*Last updated: 2026-01-24* (V9: Unified data access — `get_entity_data()`, `update_entity_data()`)
