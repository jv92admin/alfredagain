# Backend Skill

> **Scope:** Backend development — CRUD implementation, database patterns, API endpoints

This skill applies when working on FastAPI routes, database operations, Supabase integration, or backend Python code.

---

## Core Architecture

- **Framework:** FastAPI
- **Database:** Supabase (Postgres + pgvector)
- **Auth:** Google OAuth via Supabase Auth (RLS enforced)

---

## Database Patterns

### Client Access

```python
from alfred.db.client import get_client, get_service_client

# User requests (RLS enforced)
client = get_client()  # Auto-detects auth token from context

# Background tasks (RLS bypassed)
client = get_service_client()
```

**Never bypass RLS with `get_service_client()` for user-facing requests.**

### Entity Tables

| Table | Key Fields | Notes |
|-------|------------|-------|
| `recipes` | name, description, servings, total_time | Has `embedding` column for semantic search |
| `recipe_ingredients` | recipe_id (FK), ingredient_id (FK), quantity, unit | Linked table |
| `ingredients` | name | Has `embedding` column |
| `inventory` | ingredient_id (FK), quantity, unit, location, expiry | Smart ingredient lookup |
| `shopping_list` | ingredient_id (FK), quantity, checked | Smart ingredient lookup |
| `meal_plans` | date, meal_type, recipe_id (FK) | References recipes |
| `tasks` | title, description, due_date, completed | Optional meal/recipe links |
| `preferences` | User preferences and profile |

### Smart Ingredient Lookup

For `inventory` and `shopping_list`, `name = "X"` automatically uses ingredient matching:

```python
# LLM requests: {"field": "name", "op": "=", "value": "chicken"}
# System executes:
# 1. lookup_ingredient("chicken") → finds ingredient_ids
# 2. WHERE ingredient_id IN (...) OR name ILIKE '%chicken%'
# 3. Returns: chicken, chicken breasts, chicken thighs
```

### Semantic Search

`db_read` supports `_semantic` filter for vector similarity:

```python
filters=[{"field": "_semantic", "op": "similar", "value": "light summer dinner"}]
```

**Supported tables:** `recipes`, `ingredients` (have `embedding` column)

---

## API Implementation

### Schema-Driven CRUD

All entity endpoints use shared schema system:

**Files:**
- `src/alfred/web/entity_routes.py` — CRUD endpoints
- `src/alfred/models/entities.py` — Pydantic models, schemas

```python
# Endpoints follow pattern:
GET    /api/{entity_type}         # List all
GET    /api/{entity_type}/{id}    # Get one
POST   /api/{entity_type}         # Create
PUT    /api/{entity_type}/{id}    # Update
DELETE /api/{entity_type}/{id}    # Delete
```

Entity types: `recipes`, `inventory`, `shopping`, `meal-plans`, `tasks`

### Chat Endpoint

```python
# src/alfred/web/app.py
@router.post("/api/chat")
async def chat(request: ChatRequest):
    response, conversation = await run_alfred(
        user_message=request.message,
        user_id=user_id,  # From JWT
        conversation=request.conversation,
        ui_changes=request.ui_changes,
    )
    return ChatResponse(response=response, conversation=conversation)
```

### Auth Middleware

JWT validation in `src/alfred/web/app.py`:
- Extract token from `Authorization: Bearer <token>`
- Validate via Supabase
- Set user_id in request context

---

## CRUD Layer

**Location:** `src/alfred/tools/crud.py`

Key functions:
- `db_read(table, filters, limit)` — Query with ID translation
- `db_create(table, data)` — Insert with ID registration
- `db_update(table, filters, data)` — Update with translation
- `db_delete(table, filters)` — Delete with translation

### ID Translation (Automatic)

```python
# Input (from LLM):
db_delete("recipes", [{"field": "id", "op": "=", "value": "recipe_1"}])

# CRUD layer translates:
db_delete("recipes", [{"field": "id", "op": "=", "value": "abc123-uuid..."}])
```

---

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

---

## Key Files

| File | Purpose |
|------|---------|
| `src/alfred/web/app.py` | FastAPI application, auth middleware |
| `src/alfred/web/entity_routes.py` | CRUD endpoints |
| `src/alfred/db/client.py` | Database client factory |
| `src/alfred/db/embeddings.py` | Vector embedding generation |
| `src/alfred/tools/crud.py` | CRUD with ID translation |
| `src/alfred/models/entities.py` | Pydantic models, schemas |

---

## Commands

```bash
# Run server
alfred serve           # FastAPI on :8000

# Testing
pytest                 # All tests
pytest tests/test_graph.py  # Single file
pytest -k "test_name"  # By name

# Quality
ruff check src/        # Lint
ruff format src/       # Format
mypy src/              # Type check
```

---

## Related Docs

- [docs/architecture/overview.md](../../docs/architecture/overview.md) — System architecture
- [docs/specs/context-api-spec.md](../../docs/specs/context-api-spec.md) — Context API details
