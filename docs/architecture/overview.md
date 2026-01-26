# Alfred Architecture Overview

> Entry point for understanding Alfred's technical architecture.

---

## Quick Links

| Doc | Purpose |
|-----|---------|
| [ROADMAP.md](../ROADMAP.md) | What's happening — active work, backlog |
| [context-and-session.md](context-and-session.md) | Context engineering, SessionIdRegistry |
| [capabilities.md](capabilities.md) | User-facing capabilities |
| [../specs/context-api-spec.md](../specs/context-api-spec.md) | Context API builders |

---

## What is Alfred?

Alfred is a **multi-agent conversational assistant** for kitchen management: inventory, recipes, meal planning, shopping, and tasks.

### Core Principles

| Principle | Implementation |
|-----------|----------------|
| **Deterministic state** | CRUD layer + SessionIdRegistry own entity lifecycle |
| **LLMs interpret, don't own** | Understand/Think/Act reason; system enforces |
| **Simple refs, no UUIDs** | LLMs see `recipe_1`, system handles `abc123-uuid` |
| **Dynamic prompts** | Step type + subdomain → tailored guidance |

---

## Graph Flow

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
| **Think** | Conversation architect: plan steps, propose checkpoints | `steps[]`, `decision` |
| **Act** | Execute via CRUD or generate content | Tool calls, `step_complete` |
| **Reply** | Present execution results beautifully | Natural language response |
| **Summarize** | Compress context, persist registry | Updated conversation |

---

## Step Types

| Type | Purpose | DB Calls? |
|------|---------|-----------|
| `read` | Fetch data | Yes |
| `write` | Persist content | Yes |
| `analyze` | Reason over data | No |
| `generate` | Create new content | No |

**Key insight:** `generate` creates content; `write` persists it.

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

## Quick Mode

Bypasses Think for simple **single-table, read-only, data lookup** queries.

**Criteria (ALL must be true):**
1. Single table — not joins
2. Read only — no writes
3. Data lookup — answer is IN the database, not knowledge/reasoning

---

## Three-Layer Context Model

| Layer | What | Owner | Survives Turns? |
|-------|------|-------|-----------------|
| **Entity** | Refs, labels, status | SessionIdRegistry | Yes |
| **Conversation** | User/assistant messages | Summarize | Yes |
| **Reasoning** | TurnExecutionSummary | Summarize | Yes (last 2) |

See [context-and-session.md](context-and-session.md) for details.

---

## Authentication

Google OAuth via Supabase Auth with database-enforced RLS.

| Client | When Used | RLS |
|--------|-----------|-----|
| `get_client()` | User requests | Enforced |
| `get_service_client()` | Background tasks | Bypassed |

---

## File Structure

```
alfred/
├── src/alfred/
│   ├── core/id_registry.py      # SessionIdRegistry
│   ├── graph/
│   │   ├── state.py             # AlfredState
│   │   ├── workflow.py          # LangGraph definition
│   │   └── nodes/               # Node implementations
│   ├── tools/crud.py            # CRUD + ID translation
│   ├── context/builders.py      # Context API
│   └── prompts/injection.py     # Prompt assembly
├── prompts/                     # Runtime templates
└── docs/                        # Documentation
```

---

## Model Routing

| Complexity | Model | Use Case |
|------------|-------|----------|
| low | gpt-4.1-mini | Simple reads, replies |
| medium | gpt-4.1 | Cross-domain queries |
| high | gpt-4.1 | Complex generation |
