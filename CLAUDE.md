# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alfred is a LangGraph-based multi-agent assistant for kitchen management (pantry, recipes, meal planning). It uses a pipeline: Understand → Think → Act (loop) → Reply → Summarize.

**Core Principle:** Deterministic systems manage state. LLMs interpret and decide. The CRUD layer + SessionIdRegistry own entity lifecycle; LLMs (Understand/Think/Act) reason over that state.

## Development Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# Run CLI
alfred health     # Check configuration
alfred chat       # Interactive chat

# Run web server
alfred serve      # FastAPI server on port 8000

# Testing
pytest                          # All tests
pytest tests/test_graph.py      # Single file
pytest -k "test_name"           # Single test by name

# Code quality
ruff check src/                 # Lint
ruff format src/                # Format
mypy src/                       # Type check

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                     # Vite dev server
```

## Architecture

### Graph Flow

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

### Node Responsibilities

| Node | Purpose | Key Output |
|------|---------|------------|
| **Understand** | Memory manager: entity resolution ("that recipe" → `recipe_1`), context curation, quick mode detection | `referenced_entities`, `entity_curation` |
| **Think** | Conversation architect: plan steps, propose checkpoints, manage multi-turn flows | `steps[]`, `decision` (plan_direct/propose/clarify) |
| **Act** | Execute via CRUD tools or generate content | Tool calls, `step_complete` |
| **Reply** | Present execution results with persona | Natural language response |
| **Summarize** | Compress context, persist registry and conversation | Updated conversation state |

### Step Types

| Type | Purpose | DB Calls? |
|------|---------|-----------|
| `read` | Fetch data from database | Yes |
| `write` | Persist content to database | Yes |
| `analyze` | Reason over data | No |
| `generate` | Create new content (stored as pending artifact) | No |

**Key insight:** `generate` creates content; `write` persists it. Never use `write` to create new content.

### Subdomains

| Subdomain | Tables |
|-----------|--------|
| inventory | `inventory`, `ingredients` |
| recipes | `recipes`, `recipe_ingredients` |
| shopping | `shopping_list` |
| meal_plans | `meal_plans` |
| tasks | `tasks` |
| preferences | `preferences` |

## Entity Management (SessionIdRegistry)

**Single source of truth.** LLMs never see UUIDs — only simple refs like `recipe_1`, `gen_recipe_1`.

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

All nodes now see generated content (`pending_artifacts`). Reply can display generated recipes when users ask "show me that recipe".

### Three-Layer Context Model

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

## Key Files

| File | Purpose |
|------|---------|
| `src/alfred/graph/workflow.py` | LangGraph definition, `run_alfred()` entry point |
| `src/alfred/graph/state.py` | `AlfredState` TypedDict, all Pydantic contracts |
| `src/alfred/core/id_registry.py` | SessionIdRegistry — ref↔UUID translation, artifact storage |
| `src/alfred/tools/crud.py` | CRUD operations with ID translation, FK enrichment |
| `src/alfred/context/builders.py` | Context API: `build_reply_context()`, node-specific context builders |
| `src/alfred/context/entity.py` | EntityContext, EntitySnapshot, `format_entity_context()` |
| `src/alfred/context/reasoning.py` | ReasoningTrace, TurnExecutionSummary |
| `src/alfred/context/conversation.py` | ConversationHistory formatting |
| `src/alfred/prompts/injection.py` | Dynamic prompt assembly |
| `prompts/*.md` | Markdown prompt templates loaded at runtime |

## Database

Supabase (Postgres + pgvector). Authentication via Google OAuth with database-enforced RLS.

### Key Tables
- `recipes`, `recipe_ingredients` (with FK to ingredients)
- `inventory`, `shopping_list` (smart ingredient lookup)
- `meal_plans` (references recipe_id)
- `tasks`, `preferences`

### Semantic Search

`db_read` supports `_semantic` filter for vector similarity:
```python
filters=[{"field": "_semantic", "op": "similar", "value": "light summer dinner"}]
```
Uses pgvector embeddings on recipes table.

### Smart Ingredient Lookup

For `inventory` and `shopping_list`, `name = "chicken"` automatically uses ingredient lookup:
```python
# LLM requests
{"field": "name", "op": "=", "value": "chicken"}
# System finds chicken, chicken breasts, chicken thighs via ingredient_id matching
```

## Testing Patterns

```python
@pytest.mark.asyncio
async def test_workflow():
    response, conv = await run_alfred(
        user_message="Show my inventory",
        user_id="test_user_123",
    )
    assert "inventory" in response.lower()

# Multi-turn test pattern
response1, conv = await run_alfred("Add eggs", user_id="test")
response2, conv = await run_alfred("Show inventory", user_id="test", conversation=conv)
```

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/architecture_overview.md` | High-level architecture, version history |
| `docs/context-engineering-architecture.md` | Detailed context management, state vs context |
| `docs/session-id-registry-spec.md` | SessionIdRegistry implementation details |
