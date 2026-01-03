# Alfred V3 - Architecture Overview

**Document Type:** Architecture Documentation  
**Last Updated:** January 2, 2026  
**Status:** V3.1 with Quick Mode, Async Summarize, Entity Lifecycle, Step Type Taxonomy

---

## 1. Project Summary

Alfred is a **multi-agent conversational assistant** built on a LangGraph architecture with generic CRUD tools and Supabase as the persistence layer.

### Agent Architecture

The system supports multiple specialized agents, with **Router** classifying user intent and dispatching to the appropriate agent:

| Agent | Domain | Status |
|-------|--------|--------|
| **Pantry** | Kitchen: inventory, recipes, meal planning, shopping, tasks | ✅ Active |
| **Coach** | Fitness: workouts, nutrition tracking, goals | 🔲 Stub only |
| **Cellar** | Wine: collection, pairings, tasting notes | 🔲 Stub only |

The current implementation focuses on the **Pantry agent** as the proof-of-concept.

### Design Philosophy

| Principle | Implementation |
|-----------|----------------|
| Trust the LLM | Few examples, clear instructions |
| Generic tools | 4 CRUD primitives instead of domain-specific tools |
| Subdomain filtering | LLM sees only relevant tables per step |
| Schema auto-generation | From database, never stale |
| Persona over rules | Identity-based guidance vs. exhaustive warnings |
| Clear decision ownership | Each node has explicit responsibilities |

---

## 2. Graph Flow (V3 + Quick Mode)

```
                              ┌─────────────┐
                              │  ACT QUICK  │ ← Single tool call
                              └──────┬──────┘
                                     │
┌────────────┐   quick_mode?   ┌─────▼─────┐   ┌───────────┐
│ UNDERSTAND │───────────────▶│   REPLY   │──▶│ SUMMARIZE │ (async)
└─────┬──────┘                 └───────────┘   └───────────┘
      │
      │ !quick_mode
      ▼
┌───────┐   ┌─────────────────┐   ┌───────┐   ┌───────────┐
│ THINK │──▶│    ACT LOOP     │──▶│ REPLY │──▶│ SUMMARIZE │ (async)
└───────┘   │ • Branch on     │   └───────┘   └───────────┘
            │   step_type     │
            │ • Execute steps │
            │ • Pass notes    │
            └─────────────────┘
```

**Note:** Router is skipped (single-agent setup). Summarize runs asynchronously after Reply.

### Node Responsibilities

| Node | Purpose | Key Decisions |
|------|---------|---------------|
| **Understand** | Detect signals, update entity states, detect quick mode | `entity_updates`, `quick_mode`, `quick_intent` |
| **Think** | Plan steps with types and groups | `steps[]`, `decision` (plan_direct/propose/clarify) |
| **Act** | Execute steps via CRUD or generate | `tool_call`, `step_complete` |
| **Act Quick** | Single-step execution for quick mode | One tool call, direct to Reply |
| **Reply** | Synthesize user-facing response | Presentation format |
| **Summarize** | Compress context, manage entities | `conversation`, `entity_registry` |

**Note:** Router is currently skipped (single-agent). Will be re-enabled for multi-agent routing.

For detailed decision architecture, see [`decision_architecture.md`](decision_architecture.md).

---

## 3. Step Type Taxonomy (V3)

| Type | Purpose | DB Calls? | What Act Does |
|------|---------|-----------|---------------|
| `read` | Fetch data from database | Yes | Calls `db_read`, returns records |
| `write` | Save EXISTING content | Yes | Calls `db_create/update/delete` |
| `analyze` | Reason over prior step data | No | Returns analysis in `step_complete.data` |
| `generate` | Create NEW content | No | Returns generated content in `step_complete.data` |

**Key distinction:**
- `generate` = LLM creates content that doesn't exist yet (recipes, plans, ideas)
- `write` = Persist content that already exists (from prior generate, archive, or user input)

### Group-Based Parallelization

Steps with the same `group` value can run in parallel:

```
Group 0: [read recipes, read inventory]  ← parallel
Group 1: [analyze: compare lists]        ← needs Group 0
Group 2: [write shopping list]           ← needs Group 1
```

---

## 4. Quick Mode Architecture

Quick Mode bypasses Think for simple, single-step queries, reducing latency from 4+ LLM calls to 2.

### Quick Mode Flow

```
Understand → Act Quick → Reply → Summarize (async)
```

vs Full Mode:

```
Understand → Think → Act (loop) → Reply → Summarize (async)
```

### Quick Mode Detection

Understand outputs `quick_mode: true` for:

| Subdomain | Read | Write | Reason |
|-----------|------|-------|--------|
| inventory | ✅ Quick | ✅ Quick | Simple table |
| shopping | ✅ Quick | ✅ Quick | Simple table |
| tasks | ✅ Quick | ✅ Quick | Optional FKs |
| recipes | ✅ Quick | ❌ Full | Linked tables (recipe_ingredients) |
| meal_plans | ✅ Quick | ❌ Full | FK refs, date logic |
| preferences | ✅ Quick | ✅ Quick | Profile updates |

### Quick Mode Output

Understand provides:
- `quick_intent`: Plaintext intent (e.g., "Show user's shopping list")
- `quick_subdomain`: Target subdomain (e.g., "shopping")

Act Quick executes a single tool call based on this intent.

### Async Summarization

Summarize runs in the background after Reply yields, so users see responses immediately without waiting for context compression.

---

## 5. Dynamic Prompt Architecture

Act prompts are dynamically constructed based on step type and subdomain.

### Prompt Layers

1. **Base mechanics** (`prompts/act/base.md`) - Tools, actions, principles
2. **Step-type rules** (`prompts/act/{step_type}.md`) - Type-specific guidance
3. **Subdomain content** - Intro + persona from `schema.py`
4. **Contextual examples** - Pattern injection from `examples.py`
5. **Dynamic context** - Schema, prev results, archive, entities

### Branch-Specific Injections

| Input | read | write | analyze | generate |
|-------|------|-------|---------|----------|
| Schema | ✅ | ✅ | ❌ | ❌ |
| Profile | ❌ | ❌ | ✅ | ✅ |
| Archive | ✅ | ✅ | ✅ | ✅ |
| Prev step results | ✅ | ✅ | ✅ | ✅ |
| Contextual examples | ✅ | ✅ | ✅ | ✅ |

### Persona Groups

| Persona | Subdomains | Focus |
|---------|------------|-------|
| **Chef** | recipes | Creative generation, organizational CRUD, linked tables |
| **Ops Manager** | inventory, shopping, preferences | Cataloging, normalization, deduplication |
| **Planner** | meal_plans, tasks | Scheduling, dependencies, coordination |

---

## 5. Entity Lifecycle Management (V3)

### Entity States

| State | Meaning |
|-------|---------|
| `PENDING` | Generated but not saved to DB |
| `ACTIVE` | Saved to DB, currently relevant |
| `INACTIVE` | Superseded or garbage collected |

### Entity Flow

```
generate step → PENDING entity (temp_id)
    ↓
write step → ACTIVE entity (real UUID)
    ↓
3 turns without reference → INACTIVE (garbage collected)
```

### Ghost Entity Prevention

- Only entities from `db_read` or `db_write` sources are promoted to `active_entities`
- `PENDING` entities from `generate`/`analyze` steps are NOT promoted
- Prevents FK constraint violations from hallucinated IDs

---

## 6. Content Archive

Generated content persists across turns for retrieval:

```python
# Turn 1: "create 3 pasta recipes"
# → Recipes generated, archived under "generated_recipes"

# Turn 2: "save those recipes"
# → Act retrieves from archive, calls db_create
```

Archive is available in **all step types** (read, write, analyze, generate).

---

## 7. Generic CRUD Tools

| Tool | Purpose | Key Params |
|------|---------|------------|
| `db_read` | Fetch rows | table, filters, or_filters, columns, limit |
| `db_create` | Insert row(s) | table, data (dict or array for batch) |
| `db_update` | Modify matching rows | table, filters, data |
| `db_delete` | Remove matching rows | table, filters |

### Filter Operators

```
=, >, <, >=, <=, in, ilike, is_null, contains
```

### Subdomain Registry

```python
SUBDOMAIN_REGISTRY = {
    "inventory": ["inventory", "ingredients"],
    "recipes": ["recipes", "recipe_ingredients", "ingredients"],
    "shopping": ["shopping_list", "ingredients"],
    "meal_plans": ["meal_plans", "tasks", "recipes"],
    "tasks": ["tasks", "meal_plans", "recipes"],
    "preferences": ["preferences", "flavor_preferences"],
}
```

---

## 8. Model Routing

### Complexity-Based Selection

| Complexity | Model | Use Case |
|------------|-------|----------|
| **low** | gpt-4.1-mini | Simple reads, quick responses |
| **medium** | gpt-4.1 | Cross-domain operations, context inference |
| **high** | gpt-4.1 | Complex generation, multi-step reasoning |

### Node Defaults

| Node | Default Complexity |
|------|-------------------|
| Router | low |
| Understand | medium |
| Think | medium |
| Act (read/write) | low |
| Act (analyze/generate) | medium/high |
| Reply | low |
| Summarize | low |

---

## 9. Conversation Context Management

### State Structure

```python
class ConversationContext:
    engagement_summary: str      # "Helping with meal planning..."
    recent_turns: list[dict]     # Last 3 full exchanges
    history_summary: str         # Compressed older turns
    active_entities: dict        # EntityRef tracking for "that recipe"
```

### Context Thresholds

| Context Type | Token Budget | Used By |
|--------------|--------------|---------|
| Condensed | 8,000 | Router, Think |
| Full | 25,000 | Act |

---

## 10. Database Schema

### Current Tables

| Table | Purpose | User-Scoped |
|-------|---------|-------------|
| `users` | Authentication/identity | N/A |
| `ingredients` | Master ingredient catalog (~2000 seeded) | No |
| `inventory` | User's pantry items | Yes |
| `recipes` | User's saved recipes | Yes |
| `recipe_ingredients` | Recipe→ingredient linking | Yes |
| `meal_plans` | Planned meals by date | Yes |
| `tasks` | To-dos, can link to meal_plan or recipe | Yes |
| `shopping_list` | Shopping list items | Yes |
| `preferences` | Dietary, allergies, equipment | Yes |
| `flavor_preferences` | Per-ingredient preference scores | Yes |
| `cooking_log` | What was cooked, ratings, notes | Yes |

### Linked Tables

| Parent | Child | Relationship |
|--------|-------|--------------|
| `recipes` | `recipe_ingredients` | Always handled together |
| `meal_plans` | `tasks` | Optional linking via meal_plan_id |
| `recipes` | `meal_plans` | FK reference via recipe_id |

---

## 11. What Works Well

| Capability | Status |
|------------|--------|
| Simple CRUD (add to pantry, check inventory) | ✅ Solid |
| Multi-item batch operations | ✅ Solid |
| Cross-domain queries (inventory → recipe → shopping) | ✅ Works |
| Recipe generation with personalization | ✅ Works |
| Recipe CRUD with ingredient linking | ✅ Works |
| Shopping list management | ✅ Works |
| Meal planning with recipe linking | ✅ Works |
| Task creation linked to meal plans | ✅ Works |
| Multi-turn conversation with context | ✅ Works |
| Entity tracking ("that recipe") | ✅ Works |
| Cross-turn content retrieval (archive) | ✅ Works |
| Dynamic persona injection | ✅ Works |
| Step notes for multi-step workflows | ✅ Works |
| Parallel step execution (same group) | ✅ Works |
| Generate → Write separation | ✅ Works |

---

## 12. File Structure

```
alfred/
├── src/alfred/
│   ├── core/
│   │   ├── entities.py       # EntityRegistry, lifecycle
│   │   └── modes.py          # Mode definitions
│   ├── graph/
│   │   ├── state.py          # AlfredState, ThinkStep, ThinkOutput
│   │   ├── workflow.py       # LangGraph definition
│   │   └── nodes/
│   │       ├── router.py
│   │       ├── understand.py # V3: Entity resolution
│   │       ├── think.py      # V3: Step types + groups
│   │       ├── act.py        # V3: Branch on step_type
│   │       ├── reply.py
│   │       └── summarize.py
│   ├── tools/
│   │   ├── crud.py           # db_read, db_create, db_update, db_delete
│   │   └── schema.py         # Subdomain registry, schema generation
│   ├── prompts/
│   │   ├── injection.py      # Dynamic prompt assembly
│   │   ├── personas.py       # Subdomain personas
│   │   └── examples.py       # Contextual pattern injection
│   ├── llm/
│   │   ├── client.py         # Instructor-wrapped OpenAI
│   │   └── model_router.py   # Complexity → model mapping
│   ├── memory/
│   │   └── conversation.py   # Context formatting, entity extraction
│   ├── observability/
│   │   └── session_logger.py # JSONL session logging
│   └── background/
│       └── profile_builder.py # Cached profile/dashboard
├── prompts/
│   ├── router.md
│   ├── understand.md         # V3
│   ├── think.md              # V3: Step types table
│   ├── act/
│   │   ├── base.md           # Core mechanics
│   │   ├── read.md
│   │   ├── write.md
│   │   ├── analyze.md
│   │   └── generate.md
│   ├── reply.md
│   └── summarize.md
└── docs/
    ├── architecture_overview.md   # This document
    └── decision_architecture.md   # Decision point reference
```

---

## 13. Related Documentation

- [`decision_architecture.md`](decision_architecture.md) - Decision points, inputs/outputs, step type taxonomy
- [`act_prompt_architecture.md`](act_prompt_architecture.md) - Dynamic prompt construction details
