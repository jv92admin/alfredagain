# Alfred Architecture Overview

**Last Updated:** January 13, 2026  
**Status:** V6 with conversation management, smart search, entity retention

---

## Quick Links

| Doc | Purpose |
|-----|---------|
| [context-engineering-architecture.md](context-engineering-architecture.md) | **How it works now** — entity management, ID translation, state vs context |
| [session-id-registry-spec.md](session-id-registry-spec.md) | Session ID registry implementation details |

---

## 1. What is Alfred?

Alfred is a **multi-agent conversational assistant** for kitchen management: inventory, recipes, meal planning, shopping, and tasks.

### Core Principles

| Principle | Implementation |
|-----------|----------------|
| **Deterministic state** | CRUD layer + SessionIdRegistry own entity lifecycle |
| **LLMs interpret, don't own** | Understand/Think/Act reason; system enforces |
| **Simple refs, no UUIDs** | LLMs see `recipe_1`, system handles `abc123-uuid` |
| **Dynamic prompts** | Step type + subdomain → tailored guidance |

---

## 2. Graph Flow

```
                              ┌─────────────┐
                              │  ACT QUICK  │ ← Single tool call
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

### Node Responsibilities

| Node | Purpose | Key Output |
|------|---------|------------|
| **Understand** | Memory manager: entity resolution, context curation, quick mode | `referenced_entities`, `entity_curation` |
| **Think** | Conversation architect: plan steps, propose checkpoints, manage multi-turn flows | `steps[]`, `decision` (plan_direct/propose/clarify) |
| **Act** | Execute via CRUD or generate, use Recent Context directly | Tool calls, `step_complete` |
| **Reply** | Present execution results beautifully | Natural language, formatted output |
| **Summarize** | Compress context, persist registry | Updated conversation |

---

## 3. Step Types

| Type | Purpose | DB Calls? |
|------|---------|-----------|
| `read` | Fetch data | Yes |
| `write` | Persist content | Yes |
| `analyze` | Reason over data | No |
| `generate` | Create new content | No |

**Key insight:** `generate` creates content; `write` persists it. Never use `write` to create.

---

## 4. Entity Management

**Single source of truth:** `SessionIdRegistry`

```
LLM sees: recipe_1, gen_recipe_1
System handles: abc123-uuid translation
```

### Entity Lifecycle

| Action | Set By |
|--------|--------|
| `read` | CRUD layer after db_read |
| `created` | CRUD layer after db_create |
| `generated` | Act node after generate step |
| `linked` | CRUD layer (FK lazy registration) |

### V5: FK Lazy Registration with Enrichment

When reading meal_plans with recipe_id FKs:
1. System lazy-registers unknown FK UUIDs (e.g., `recipe_1`)
2. Batch queries target table for names
3. Enriches display: "Butter Chicken (recipe_1)"

See [context-engineering-architecture.md](context-engineering-architecture.md) for full details.

---

## 5. Subdomains

| Subdomain | Tables | Persona |
|-----------|--------|---------|
| inventory | `inventory`, `ingredients` | Ops Manager |
| recipes | `recipes`, `recipe_ingredients` | Chef |
| shopping | `shopping_list` | Ops Manager |
| meal_plans | `meal_plans` | Planner |
| tasks | `tasks` | Planner |
| preferences | `preferences` | Personal Assistant |

---

## 6. Quick Mode

Bypasses Think for simple **single-part** queries:

| Subdomain | Read | Write |
|-----------|------|-------|
| inventory | ✅ | ✅ |
| shopping | ✅ | ✅ |
| tasks | ✅ | ✅ |
| recipes | ✅ | ❌ (linked tables) |
| meal_plans | ✅ | ❌ (FK logic) |

**V5:** Multi-part queries ("X and also Y") explicitly excluded from quick mode.

---

## 6.1 Context Layers (V7)

Alfred uses a **three-layer context model** managed by the Context API:

| Layer | What | Owner | Survives Turns? |
|-------|------|-------|-----------------|
| **Entity** | Refs, labels, status | SessionIdRegistry | ✅ Yes |
| **Conversation** | User/assistant messages | Summarize | ✅ Yes |
| **Reasoning** | What LLMs decided, TurnExecutionSummary | Summarize | ✅ Yes (last 2) |

### What Each Node Sees

| Node | Entity | Conversation | Reasoning |
|------|--------|--------------|-----------|
| **Think** | Refs + labels | Full recent, compressed older | Last 2 turn summaries |
| **Act** | Refs + labels + step results | Recent | Prior turn steps (last 2) |
| **Reply** | Labels only | Recent | Current turn summary |

### Recent Context vs Step Results

| Section | What It Contains | When Available |
|---------|------------------|----------------|
| **Recent Context** | Refs + labels only: `recipe_1: Chicken Tikka (recipe) [read]` | Always (from registry) |
| **Step Results** | Full data: metadata, ingredients, instructions | Only when read THIS turn |

**⚠️ Known Gap:** Think sees refs in "Recent Context" and may plan an analyze step assuming Act has the data. But if the entity was read in a PRIOR turn (not this turn), Act only has the ref — NOT the full data (ingredients, metadata). 

**Current guidance:** Think should plan a read step when Act needs actual entity data for analysis/generation. "Recent Context" means "we know about it" not "data is loaded."

**Future consideration:** Store condensed snapshots (metadata + ingredients) alongside refs so "Recent Context" includes usable data, not just labels.

---

## 6.2 Smart Inventory/Shopping Search (V6)

`db_read` for `inventory` and `shopping_list` now uses smart ingredient matching:

| Filter Operator | Behavior |
|-----------------|----------|
| `op: "="` | Smart single match via `ingredient_lookup` |
| `op: "similar"` | Returns top N candidates above threshold |

**Example:** `{field: "name", op: "=", value: "chicken"}` 
→ Looks up "chicken" in ingredients table
→ Finds `chicken breasts`, `chicken thighs` by ingredient_id
→ Returns all matching inventory items

LLMs don't need to know the mechanics — just use `name = "chicken"`.

---

## 7. File Structure

```
alfred/
├── src/alfred/
│   ├── core/
│   │   ├── id_registry.py    # SessionIdRegistry (THE source of truth)
│   │   └── modes.py
│   ├── graph/
│   │   ├── state.py          # AlfredState, ThinkOutput
│   │   ├── workflow.py       # LangGraph definition
│   │   └── nodes/            # understand, think, act, reply, summarize
│   ├── tools/
│   │   ├── crud.py           # CRUD + ID translation + FK enrichment
│   │   └── schema.py         # Subdomain registry
│   ├── prompts/
│   │   ├── injection.py      # Dynamic prompt assembly
│   │   ├── personas.py       # Subdomain personas
│   │   └── examples.py       # Contextual examples
│   └── memory/
│       └── conversation.py   # Context management
├── prompts/
│   ├── understand.md
│   ├── think.md
│   ├── act/                  # base.md, read.md, write.md, analyze.md, generate.md
│   ├── reply.md
│   └── summarize.md
└── docs/
    ├── architecture_overview.md           # This file
    ├── context-engineering-architecture.md  # Detailed "how it works"
    ├── session-id-registry-spec.md        # ID registry spec
    └── understand-context-management-spec.md  # V5 context curation
```

---

## 8. Model Routing

| Complexity | Model | Use Case |
|------------|-------|----------|
| low | gpt-4.1-mini | Simple reads, replies |
| medium | gpt-4.1 | Cross-domain, context inference |
| high | gpt-4.1 | Complex generation |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| V7 | 2026-01-14 | Three-layer Context API, TurnExecutionSummary, conversation continuity, generate entity context fix |
| V6 | 2026-01-13 | Think as conversation architect, Recent Context guidance, smart inventory search, entity retention fixes |
| V5 | 2026-01-10 | Understand as Memory Manager, FK enrichment, improved display |
| V4.1 | 2026-01-08 | Think prompt cleanup, deprecated unused fields |
| V4 | 2026-01-06 | SessionIdRegistry, unified entity management |
| V3 | 2026-01-02 | Step types, quick mode, async summarize |
