# Alfred Architecture Overview

**Last Updated:** January 8, 2026  
**Status:** V4 with SessionIdRegistry, unified entity management

---

## Quick Links

| Doc | Purpose |
|-----|---------|
| [context-engineering-architecture.md](context-engineering-architecture.md) | **How it works now** — entity management, ID translation, state vs context |
| [session-id-registry-spec.md](session-id-registry-spec.md) | Session ID registry implementation details |
| [v4-architecture-spec.md](v4-architecture-spec.md) | Historical V4 spec (for reference, mostly implemented) |

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
| **Understand** | Intent detection, entity resolution, quick mode | `quick_mode`, `referenced_entities` |
| **Think** | Plan steps with types and groups | `steps[]`, `decision` |
| **Act** | Execute via CRUD or generate | Tool calls, `step_complete` |
| **Reply** | Synthesize user-facing response | Natural language |
| **Summarize** | Compress context | Updated conversation |

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

Bypasses Think for simple single-step queries:

| Subdomain | Read | Write |
|-----------|------|-------|
| inventory | ✅ | ✅ |
| shopping | ✅ | ✅ |
| tasks | ✅ | ✅ |
| recipes | ✅ | ❌ (linked tables) |
| meal_plans | ✅ | ❌ (FK logic) |

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
│   │   ├── crud.py           # CRUD + ID translation
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
    ├── architecture_overview.md      # This file
    ├── context-engineering-architecture.md  # Detailed "how it works"
    └── session-id-registry-spec.md   # ID registry spec
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
| V4.1 | 2026-01-08 | Think prompt cleanup, deprecated unused fields |
| V4 | 2026-01-06 | SessionIdRegistry, unified entity management |
| V3 | 2026-01-02 | Step types, quick mode, async summarize |
