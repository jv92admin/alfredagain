# Orchestration Skill

> **Scope:** LLM orchestration — node behavior, state machines, prompts

This skill applies when working on LangGraph workflow, node implementations, prompt engineering, or context management.

---

## Graph Flow

```
                              ┌─────────────┐
                              │  ACT QUICK  │ ← Single tool call (simple reads)
                              └──────┬──────┘
                                     │
┌────────────┐   quick_mode?   ┌─────▼─────┐   ┌───────────┐
│ UNDERSTAND │───────────────▶│   REPLY   │──▶│ SUMMARIZE │
└─────┬──────┘                 └───────────┘   └───────────┘
      │
      │ !quick_mode
      ▼
┌───────┐   ┌─────────────────┐   ┌───────┐   ┌───────────┐
│ THINK │──▶│    ACT LOOP     │──▶│ REPLY │──▶│ SUMMARIZE │
└───────┘   └─────────────────┘   └───────┘   └───────────┘
```

---

## Node Responsibilities

| Node | Purpose | Key Output |
|------|---------|------------|
| **Understand** | Memory manager: entity resolution, context curation, quick mode detection | `referenced_entities`, `entity_curation` |
| **Think** | Conversation architect: plan steps, propose checkpoints, manage multi-turn flows | `steps[]`, `decision` (plan_direct/propose/clarify) |
| **Act** | Execute via CRUD tools or generate content | Tool calls, `step_complete` |
| **Reply** | Present execution results with persona | Natural language response |
| **Summarize** | Compress context, persist registry and conversation | Updated conversation state |

---

## Step Types

| Type | Purpose | DB Calls? | Content Created? |
|------|---------|-----------|------------------|
| `read` | Fetch data from database | Yes | No |
| `write` | Persist content to database | Yes | No |
| `analyze` | Reason over data | No | No |
| `generate` | Create new content (stored as pending artifact) | No | Yes |

**Key insight:** `generate` creates content; `write` persists it. Never use `write` to create new content.

---

## Subdomains

| Subdomain | Tables |
|-----------|--------|
| inventory | `inventory`, `ingredients` |
| recipes | `recipes`, `recipe_ingredients` |
| shopping | `shopping_list` |
| meal_plans | `meal_plans` |
| tasks | `tasks` |
| preferences | `preferences` |

---

## Entity Management (SessionIdRegistry)

**Single source of truth.** LLMs never see UUIDs — only simple refs.

### Ref Naming Convention
- `{type}_{n}` — Entity from database: `recipe_1`, `inv_5`, `meal_3`
- `gen_{type}_{n}` — Generated but not yet saved: `gen_recipe_1`

### Entity Lifecycle

| Action | Set By | When |
|--------|--------|------|
| `read` | CRUD layer | After `db_read` returns data |
| `created` | CRUD layer | After `db_create` succeeds |
| `updated` | CRUD layer | After `db_update` succeeds |
| `deleted` | CRUD layer | After `db_delete` succeeds |
| `generated` | Act node | After generate step produces content |
| `linked` | CRUD layer | FK lazy registration (e.g., recipe_id in meal_plans) |

### ID Translation Flow

```
db_read → SessionIdRegistry.translate_read_output() → LLM sees recipe_1
LLM says "delete recipe_1" → SessionIdRegistry.translate_filters() → db_delete with UUID
```

### V9: Unified Data Access

```python
# Single source of truth for entity data availability
registry.get_entity_data(ref) → dict | None

# Unified modification for gen_* artifacts
registry.update_entity_data(ref, content) → bool
```

---

## Three-Layer Context Model

| Layer | What | Owner | Survives Turns? |
|-------|------|-------|-----------------|
| **Entity** | Refs, labels, status | SessionIdRegistry | Yes |
| **Conversation** | User/assistant messages | Summarize | Yes |
| **Reasoning** | What LLMs decided (TurnExecutionSummary) | Summarize | Yes (last 2) |

### Entity Context Delineation in Prompts

```
## Generated Content (NOT YET SAVED)
- gen_recipe_1: Thai Curry (recipe) [unsaved]

## Recent Context (last 2 turns)
- recipe_1: Butter Chicken (recipe) [read:full]
- inv_1: Eggs (inv) [read]

## Long Term Memory (retained from earlier)
- gen_meal_plan_1: Weekly Plan (meal, turn 2) — *User's ongoing goal*
```

---

## Context API

**Location:** `src/alfred/context/`

| File | Purpose |
|------|---------|
| `entity.py` | `get_entity_context()`, `format_entity_context()` |
| `conversation.py` | `get_conversation_history()`, `format_conversation()` |
| `reasoning.py` | `get_reasoning_trace()`, `format_reasoning()` |
| `builders.py` | `build_think_context()`, `build_act_context()`, `build_reply_context()` |

### Node-Specific Builders

```python
build_understand_context(state) → dict  # Full context for curation
build_think_context(state) → dict       # Refs + labels for planning
build_act_context(state) → dict         # Full data for execution
build_reply_context(state) → dict       # Labels for presentation
```

---

## Prompt Structure

**Runtime templates:** `prompts/*.md`

| Template | Node |
|----------|------|
| `system.md` | All nodes (identity/capabilities) |
| `understand.md` | Understand node |
| `think.md` | Think node |
| `act/base.md`, `act/crud.md`, `act/*.md` | Act node (step-type specific) |
| `reply.md` | Reply node |
| `summarize.md` | Summarize node |

**Prompt assembly:** `src/alfred/prompts/injection.py`

---

## Key Files

| File | Purpose |
|------|---------|
| `src/alfred/graph/workflow.py` | LangGraph definition, `run_alfred()` entry point |
| `src/alfred/graph/state.py` | `AlfredState` TypedDict, all Pydantic contracts |
| `src/alfred/graph/nodes/*.py` | Node implementations |
| `src/alfred/core/id_registry.py` | SessionIdRegistry — ref↔UUID translation |
| `src/alfred/context/builders.py` | Context API builders |
| `src/alfred/prompts/injection.py` | Dynamic prompt assembly |

---

## Common Patterns

### Quick Mode Detection (Understand)
- Single-part request
- Single-domain
- READ only (no writes, generates, or knowledge questions)

### Think Decisions
| Decision | When |
|----------|------|
| `plan_direct` | Clear request, can execute immediately |
| `propose` | Complex workflow, present plan to user first |
| `clarify` | Ambiguous request, need more info |

### Recent Context = Already Loaded
If Think sees entities in "Recent Context (last 2 turns)":
- DON'T: Plan a read step to "read all recipes"
- DO: Plan an analyze step referencing those entities by ref

---

## Related Docs

- [docs/architecture/overview.md](../../docs/architecture/overview.md) — System architecture
- [docs/architecture/sessions-context-entities.md](../../docs/architecture/sessions-context-entities.md) — Context engineering details
- [docs/prompts/think-prompt-structure.md](../../docs/prompts/think-prompt-structure.md) — Think prompt assembly
- [docs/prompts/act-prompt-structure.md](../../docs/prompts/act-prompt-structure.md) — Act prompt assembly
