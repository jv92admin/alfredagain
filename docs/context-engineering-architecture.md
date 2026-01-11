# Alfred Context Engineering Architecture

> This document describes **how the system works**, not how it got here.
> No phases, no versions — just the current architecture.

---

## Philosophy

Alfred is a multi-agent system where LLMs interpret context but do not own state.

**Core Principle:** Deterministic systems manage state. LLMs interpret and decide.

| Layer | Responsibility | Deterministic? |
|-------|---------------|----------------|
| CRUD Layer | Database operations, ID translation, FK enrichment | ✅ Yes |
| Session Registry | Entity tracking, action history, context curation | ✅ Yes |
| Summarization | Conversation compression | Mostly ✅ |
| Understand | Context curation, entity resolution (Memory Manager) | 🤖 LLM |
| Think | Planning | 🤖 LLM |
| Act | Execution | 🤖 LLM |
| Reply | Response synthesis | 🤖 LLM |

---

## 1. Entity Management

### What is an Entity?

An entity is anything with an ID that persists: recipes, inventory items, meal plans, tasks.

### Single Source of Truth: `SessionIdRegistry`

**One system. No alternatives.**

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
│   ref_source_step:  gen_recipe_1 → 2                       │
│                                                             │
│ GENERATED CONTENT                                           │
│   pending_artifacts: gen_recipe_1 → {full JSON content}    │
│                                                             │
│ V5: CONTEXT CURATION                                        │
│   ref_active_reason: gen_meal_plan_1 → "User's ongoing goal"│
│   _lazy_enrich_queue: {ref: (table, name_col)} (transient) │
└─────────────────────────────────────────────────────────────┘
```

### Entity Lifecycle (Deterministic)

| Action | Set By | Where |
|--------|--------|-------|
| `read` | CRUD layer | `translate_read_output()` |
| `created` | CRUD layer | `register_created()` |
| `updated` | CRUD layer | After `db_update` succeeds |
| `deleted` | CRUD layer | After `db_delete` succeeds |
| `generated` | Act node | `register_generated()` |
| `linked` | CRUD layer | FK lazy registration |

**No LLM involvement in entity lifecycle tracking.**

### V5: FK Lazy Registration with Enrichment

When `db_read` returns records with FK fields (e.g., meal_plans with recipe_id):

1. **Lazy Registration:** Unknown FK UUIDs get refs immediately (no UUID leaks)
2. **Batch Enrichment:** `_enrich_lazy_registrations()` queries target tables for names
3. **Label Update:** `ref_labels` populated with real names ("Butter Chicken")
4. **Display Enrichment:** `_add_enriched_labels()` adds `_*_label` fields to result

**Works for:** recipes, ingredients, tasks (anything with name/title column)

### View Methods (Presentation, Not Storage)

Instead of separate data structures, `SessionIdRegistry` provides views:

| Method | Purpose |
|--------|---------|
| `format_for_act_prompt()` | Entities for current step (delineated: pending, recent, long-term) |
| `format_for_understand_prompt()` | Full context with turn annotations |
| `format_for_think_prompt()` | Entity summary for planning (delineated sections) |
| `get_entities_this_turn()` | Filter by current turn |
| `get_active_entities(turns_window)` | Returns (recent_refs, retained_refs) tuple |

---

## 2. ID Management

### The Problem We Solved

LLMs should never see UUIDs. They're hard to work with and easy to hallucinate.

### The Solution

| What LLMs See | What DB Uses | Translation Layer |
|---------------|--------------|-------------------|
| `recipe_1` | `abc123-...` | `SessionIdRegistry` |
| `gen_recipe_1` | (pending) | `SessionIdRegistry` |
| `inv_5` | `def456-...` | `SessionIdRegistry` |

### ID Flow

```
db_read → SessionIdRegistry.translate_read_output() → LLM sees recipe_1
       → _enrich_lazy_registrations() → FK names fetched
       → _add_enriched_labels() → result has _recipe_id_label

LLM says "delete recipe_1" → SessionIdRegistry.translate_filters() → db_delete with UUID
```

**100% deterministic. No LLM guessing IDs.**

---

## 3. Turn and Step Context Management

### Definitions

| Term | Scope | What It Contains |
|------|-------|------------------|
| **Session** | Multiple conversations | User preferences, persistent state |
| **Turn** | One user message → one assistant response | All steps executed |
| **Step** | One operation within a turn | Read/Write/Analyze/Generate |

### What Each Node Receives

| Node | Receives | Uses For |
|------|----------|----------|
| **Understand** | User message, annotated conversation, previous decisions | Context curation, entity resolution |
| **Think** | Goal, delineated entity context, dashboard | Planning steps |
| **Act** | Step description, prior step results, delineated entities | Executing one step |
| **Reply** | Execution summary, step results | Synthesizing response |
| **Summarize** | Full response, execution results, registry | Persisting state |

### V5: Understand as Memory Manager

Understand's primary role is **context curation**, not message rewriting.

**What Understand Does:**
- Reference resolution: "that recipe" → `recipe_1`
- Context curation: decide what stays active beyond 2-turn window
- Retention decisions: explain WHY older entities should persist
- Quick mode detection (single-part, single-domain READ only)

**What Understand Does NOT Do:**
- Rewrite/interpret user message (removed `processed_message`)
- Give instructions to Think
- Look up UUIDs

### Entity Context Delineation

Both Think and Act see entities in delineated sections:

```
## ⚠️ Generated (NOT YET SAVED)
- gen_recipe_1: Thai Curry (recipe) [needs save]

## Recent Context (last 2 turns)
- recipe_1: Butter Chicken (recipe) [read]
- inv_1: Eggs (inv) [read]

## Long Term Memory (retained from earlier)
- gen_meal_plan_1: Weekly Plan (meal, turn 2) — *User's ongoing goal*
```

---

## 4. Dynamic Prompt Injection

### Step Type System

| Step Type | Purpose | Prompt Injections |
|-----------|---------|-------------------|
| `read` | Query database | Schema, filter examples |
| `write` | Modify database | Schema, FK patterns, content to save |
| `analyze` | Reason over data | Prior step results, analysis framework |
| `generate` | Create content | User preferences, constraints, examples |

### Subdomain System

Each subdomain (recipes, inventory, meal_plans, etc.) has:
- Schema information
- Domain-specific patterns
- Example queries/operations

### V5: Step-Scoped Schema Injection

Act only sees schema for tables relevant to current step:
- meal_plans step → meal_plans schema only (not recipes)
- Prevents Act from overstepping step scope

### Display Formatting

| Entity Type | Display Format |
|-------------|----------------|
| Recipes | `- Butter Chicken total_time:45min id:recipe_1` |
| Meal Plans | `- 2026-01-12 [lunch] → Butter Chicken (recipe_1) id:meal_1` |
| Inventory | `- Eggs (12 count) [fridge] id:inv_1` |
| Tasks | `- Buy groceries @2026-01-15 [pending] id:task_1` |

---

## 5. State vs Context

### Definitions

| Term | Meaning | Who Owns It |
|------|---------|-------------|
| **State** | Ground truth, persisted, deterministic | System (DB, Registry) |
| **Context** | Interpreted, curated, probabilistic | LLMs (Understand, Think) |

### Per-Node Breakdown

| Node | Reads State | Reads Context | Writes State | Writes Context |
|------|-------------|---------------|--------------|----------------|
| Understand | Entity registry | Conversation history | - | Entity curation decisions |
| Think | Dashboard, constraints | Entity context, user intent | - | Execution plan |
| Act | Schema, registry | Prior steps, step description | DB via CRUD | Step results |
| Reply | Execution results | - | - | Final response |
| Summarize | Execution facts | - | Conversation history, registry | - |

### The Key Insight

**State changes are deterministic:**
- `db_create` succeeded → entity is `created`
- `db_delete` succeeded → entity is removed
- No LLM decides this.

**Context is interpreted:**
- "that recipe" → Understand resolves to `recipe_1`
- "I want something spicy" → Think incorporates into plan
- LLMs make these calls.

---

## 6. V5 Enhancements Summary

| Feature | Implementation |
|---------|----------------|
| Understand as Memory Manager | Removed `processed_message`, added context curation |
| Long-term entity retention | `ref_active_reason` stores WHY older entities stay active |
| FK lazy registration | Unknown FK UUIDs get refs immediately |
| Batch name enrichment | `_enrich_lazy_registrations()` queries for names |
| Post-process labels | `_add_enriched_labels()` adds labels after enrichment |
| Delineated entity sections | Pending → Recent → Long Term Memory |
| Entity-type labels | `_compute_entity_label()` for type-specific formatting |
| Meal plan display | `date [slot] → recipe_name (ref) id:meal_X` |
| Multi-part query exclusion | "X and Y" explicitly not quick mode |

---

## Critical Insights

### Refs vs Content

**What SessionIdRegistry stores per entity:**
- ✅ Ref → UUID mapping
- ✅ Label (e.g., "Butter Chicken")
- ✅ Type, last action, turn info
- ❌ Full entity content (e.g., quantity, location, all fields)

**Implication for Think's planning:**

| Step Type | What Act Needs | Refs Sufficient? |
|-----------|----------------|------------------|
| write/delete | Just the ref | ✅ Yes |
| generate | Labels + general context | ✅ Yes |
| analyze (compare/match) | **Full row data** | ❌ No — read first! |

### Dashboard ≠ Context

**Dashboard** shows what exists in the database (e.g., "1 saved recipe").
**Entities in Context** shows what has refs registered in SessionIdRegistry.

If an entity appears in Dashboard but NOT in "Entities in Context":
- Think cannot use a ref for it (e.g., `recipe_1` doesn't exist)
- Think must search by NAME, not by ref

### Linked Entities

Entities discovered via FK (e.g., recipe_id in meal_plans):
- Registered with action `linked`
- Filtered from active entity lists
- Shown inline with parent records only

---

*Last updated: 2026-01-10*
