# Context Engineering & Session Registry

> How Alfred manages entity state, context, and ID translation.

---

## Philosophy

Alfred is a multi-agent system where **LLMs interpret context but do not own state**.

| Layer | Responsibility | Deterministic? |
|-------|---------------|----------------|
| CRUD Layer | Database operations, ID translation | Yes |
| Session Registry | Entity tracking, action history | Yes |
| Summarization | Conversation compression | Mostly |
| Understand | Context curation (Memory Manager) | LLM |
| Think | Planning | LLM |
| Act | Execution | LLM |
| Reply | Response synthesis | LLM |

---

## SessionIdRegistry

**Single source of truth** for entity ID management.

### Core Data

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionIdRegistry                        │
├─────────────────────────────────────────────────────────────┤
│ CORE ID MAPPING                                             │
│   ref_to_uuid:      recipe_1 → abc123-uuid...              │
│   uuid_to_ref:      abc123-uuid... → recipe_1              │
│                                                             │
│ ENTITY METADATA                                             │
│   ref_actions:      recipe_1 → "created"                   │
│   ref_labels:       recipe_1 → "Butter Chicken"            │
│   ref_types:        recipe_1 → "recipe"                    │
│                                                             │
│ TEMPORAL TRACKING                                           │
│   ref_turn_created: recipe_1 → 3                           │
│   ref_turn_last_ref: recipe_1 → 5                          │
│                                                             │
│ GENERATED CONTENT                                           │
│   pending_artifacts: gen_recipe_1 → {full JSON content}    │
│                                                             │
│ CONTEXT CURATION                                            │
│   ref_active_reason: gen_meal_plan_1 → "User's ongoing goal"│
└─────────────────────────────────────────────────────────────┘
```

### Ref Naming Convention

- `{type}_{n}` — Entity from database: `recipe_1`, `inv_5`
- `gen_{type}_{n}` — Generated but not yet saved: `gen_recipe_1`

### Entity Lifecycle

| Action | Set By | When |
|--------|--------|------|
| `read` | CRUD layer | After `db_read` returns data |
| `created` | CRUD layer | After `db_create` succeeds |
| `updated` | CRUD layer | After `db_update` succeeds |
| `deleted` | CRUD layer | After `db_delete` succeeds |
| `generated` | Act node | After generate step produces content |
| `linked` | CRUD layer | FK lazy registration |
| `created:user` | UI | User created via frontend |
| `mentioned:user` | Chat | User @-mentioned entity |

---

## ID Translation

### The Problem

LLMs should never see UUIDs — they're hard to work with and easy to hallucinate.

### The Solution

```
db_read → SessionIdRegistry.translate_read_output() → LLM sees recipe_1
LLM says "delete recipe_1" → SessionIdRegistry.translate_filters() → db_delete with UUID
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `translate_read_output(records, table)` | UUIDs → refs, lazy register FKs |
| `translate_filters(filters)` | refs → UUIDs for queries |
| `translate_payload(data, table)` | refs → UUIDs for create/update |

---

## FK Lazy Registration

When `db_read` returns records with FK fields (e.g., meal_plans with recipe_id):

1. **Lazy Registration:** Unknown FK UUIDs get refs immediately
2. **Batch Enrichment:** Query target tables for names
3. **Label Update:** `ref_labels` populated with real names
4. **Display Enrichment:** `_*_label` fields added to result

```
db_read("meal_plans") returns recipe_id: "recipe-uuid-xyz"
    ↓
System: recipe_id not in registry → assign recipe_1
    ↓
Batch query: SELECT name FROM recipes WHERE id = 'recipe-uuid-xyz'
    ↓
Label: recipe_1 → "Butter Chicken"
    ↓
LLM sees: recipe_id: "recipe_1", _recipe_id_label: "Butter Chicken"
```

---

## Unified Data Access (V9)

```python
# Single source of truth for entity data availability
registry.get_entity_data(ref) → dict | None

# Unified modification for gen_* artifacts
registry.update_entity_data(ref, content) → bool
```

All nodes see generated content (`pending_artifacts`). Reply can display generated recipes when users ask "show me that recipe".

### Smart Read Rerouting for gen_* Refs

Think can plan `read gen_recipe_1` — the CRUD layer detects the pending ref and returns from `pending_artifacts` instead of querying the database.

**Uniform mental model:** "Need data? Read it." Works for both DB entities and generated content.

---

## Three-Layer Context Model

| Layer | What | Owner | Survives Turns? |
|-------|------|-------|-----------------|
| **Entity** | Refs, labels, status | SessionIdRegistry | Yes |
| **Conversation** | User/assistant messages | Summarize | Yes |
| **Reasoning** | TurnExecutionSummary | Summarize | Yes (last 2) |

### Context API Files

```
src/alfred/context/
├── entity.py        # get_entity_context(), format_entity_context()
├── conversation.py  # get_conversation_history()
├── reasoning.py     # get_reasoning_trace(), TurnExecutionSummary
└── builders.py      # build_think_context(), build_act_context(), etc.
```

### Node-Specific Builders

```python
build_understand_context(state) → dict  # Full context for curation
build_think_context(state) → dict       # Refs + labels for planning
build_act_context(state) → dict         # Full data for execution
build_reply_context(state) → dict       # Labels for presentation
```

### Per-Node Context Consumption

| Node | Entity Layer | Conversation | Reasoning | Generated |
|------|--------------|--------------|-----------|-----------|
| **Understand** | Full (all tiers) | Full + pending | Own history | Full |
| **Think** | Refs + labels | Recent + summary | Last 2 turns | Refs + labels |
| **Act** | Full data | Recent only | Current turn | Full JSON |
| **Reply** | Labels only | Recent | Outcomes | Full JSON |

---

## Entity Context Delineation

Both Think and Act see entities in delineated sections:

```
## Generated (NOT YET SAVED)
- gen_recipe_1: Thai Curry (recipe) [needs save]

## Recent Context (last 2 turns)
**Already loaded. Do NOT re-read them.**
- recipe_1: Butter Chicken (recipe) [read]
- inv_1: Eggs (inv) [read]

## Long Term Memory (retained from earlier)
- gen_meal_plan_1: Weekly Plan (meal, turn 2) — *User's ongoing goal*
```

### Key Insight

Entities in Recent Context are already in memory:
- DON'T: Plan a read step to "read all recipes"
- DO: Plan an analyze step referencing those entities by ref

### Refs vs Content (The Gap)

**What SessionIdRegistry stores:**
- Ref → UUID mapping
- Label (e.g., "Butter Chicken")
- Type, last action, turn info
- **NOT** full entity content (ingredients, instructions)

**What step_results stores:**
- Full entity content from reads
- **Does NOT survive turns** (wiped when Think creates new plan)

**Implication for Think's planning:**

| Step Type | What Act Needs | Refs Sufficient? |
|-----------|----------------|------------------|
| write/delete | Just the ref | Yes |
| generate (meal plan) | Refs as recipe_id | Yes |
| generate (with substitutions) | Full instructions | **No — read first!** |
| analyze (compare/match) | Full row data | **No — read first!** |

### Dashboard ≠ Context

**Dashboard** shows what exists in the database (e.g., "1 saved recipe").
**Entities in Context** shows what has refs registered in SessionIdRegistry.

If an entity appears in Dashboard but NOT in context:
- Think cannot use a ref for it (`recipe_1` doesn't exist yet)
- Think must search by NAME, not by ref

---

## State vs Context

| Term | Meaning | Who Owns It |
|------|---------|-------------|
| **State** | Ground truth, persisted, deterministic | System (DB, Registry) |
| **Context** | Interpreted, curated, probabilistic | LLMs |

**State changes are deterministic:**
- `db_create` succeeded → entity is `created`
- No LLM decides this

**Context is interpreted:**
- "that recipe" → Understand resolves to `recipe_1`
- LLMs make these calls

---

## Frontend → Context Integration

How UI actions flow into the AI's context layer.

### UI Change Tracking

When users make changes via the UI, the frontend tracks them:

```typescript
// Frontend: ChatContext.tsx
pushUIChange({
  entity_type: "recipe",
  entity_id: "uuid-123",
  action: "created",      // created | updated | deleted
  label: "Butter Chicken"
});
```

These are sent with the next chat message:

```
POST /api/chat
{
  "message": "Add this to my meal plan",
  "ui_changes": [
    { "entity_type": "recipe", "entity_id": "uuid-123", "action": "created", "label": "Butter Chicken" }
  ]
}
```

### Backend Registration

The backend registers UI changes into SessionIdRegistry:

```python
# src/alfred/core/id_registry.py
registry.register_from_ui(
    uuid="uuid-123",
    entity_type="recipe",
    label="Butter Chicken",
    action="created:user"  # Note: ":user" suffix distinguishes from AI actions
)
```

**Result:** AI sees `recipe_1: Butter Chicken [created:user]` in context.

### @-Mention Injection

When users @-mention entities:

```
Frontend: User types "@[Butter Chicken](recipe:uuid-123)"
    ↓
Chat request includes:
{
  "mentioned_entities": [{
    "ref_type": "recipe",
    "uuid": "uuid-123",
    "label": "Butter Chicken",
    "data": { /* full entity data */ }
  }]
}
    ↓
Backend: register_from_ui() with action="mentioned:user"
    ↓
AI sees: Full entity data injected into context
```

### Action Tags Reference

| Tag | Source | Meaning |
|-----|--------|---------|
| `read` | AI via CRUD | Entity fetched by AI |
| `created` | AI via CRUD | AI created entity |
| `created:user` | UI | User created via form |
| `updated:user` | UI | User edited via form |
| `deleted:user` | UI | User deleted via UI |
| `mentioned:user` | Chat | User @-mentioned in chat |

---

## Smart Search Features

### Semantic Search (recipes, ingredients)

```python
filters=[{"field": "_semantic", "op": "similar", "value": "light summer dinner"}]
```

Uses pgvector embeddings. Semantic narrows first, then exact filters refine.

### Smart Ingredient Lookup (inventory, shopping)

```python
{"field": "name", "op": "=", "value": "chicken"}
# → Finds: chicken, chicken breasts, chicken thighs via ingredient_id
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/alfred/core/id_registry.py` | SessionIdRegistry implementation |
| `src/alfred/tools/crud.py` | CRUD layer with ID translation |
| `src/alfred/context/builders.py` | Context API builders |
| `src/alfred/graph/nodes/summarize.py` | Persists registry to conversation |
