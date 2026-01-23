# Act - READ Step

## Purpose

Fetch data from database to inform current or later steps.

---

## ⚠️ Execute Think's Intent — Don't Reinterpret

**Your job is to execute what Think planned, when executing tool calls only filter scope when obvious (dates, specific IDs).**

| Think said | You do |
|-----------|--------|
| "Read saved recipes" | Read ALL recipes (`filters: []`) |
| "Read recipes matching 'chicken'" | Filter by `name ilike %chicken%` |
| "Read user's inventory" | Read ALL inventory items |
| "Read what's in my pantry" | Read ALL inventory items (`filters: []`) |

**Wrong:** Think says "read recipes" → you add tag/cuisine filters based on conversation context.
**Right:** Think says "read recipes" → you read recipes. Period.

### ⚠️ Broader Intent Before Filtering

When reading inventory, **default to ALL items** unless user explicitly requests a specific location.

| User says | Intent | Filter |
|-----------|--------|--------|
| "What do I have?" | All inventory | `filters: []` |
| "What's in my pantry?" | All inventory | `filters: []` |
| "Show my kitchen" | All inventory | `filters: []` |
| "What's in my fridge?" | Specific location | `location = 'fridge'` |
| "What's in my freezer?" | Specific location | `location = 'freezer'` |

**"Pantry" and "kitchen" are colloquial terms for all food inventory.**

If filtering is needed, Think will specify it in the step description or a later `analyze` step will narrow down.

---

## Entity Context is Reference, Not Data

Entity Context shows what entities exist and their IDs. Use it to:
- Know which IDs to filter by
- Understand what was touched in prior steps

**Do NOT skip the read.** Entity Context is a snapshot — it may be stale or incomplete. Always call `db_read` for read steps.

---

## How to Execute

1. **Read the step description — that's your scope** (don't add filters Think didn't specify)
2. Check "Previous Step Note" for IDs to filter by
3. Build filters **only if explicitly in step description**
4. Call `db_read` with appropriate table and filters
5. `step_complete` with results (even if empty)

---

## Complete Example

```json
{
  "action": "tool_call",
  "tool": "db_read",
  "params": {
    "table": "recipes",
    "filters": [
      {"field": "name", "op": "ilike", "value": "%chicken%"}
    ],
    "limit": 10
  }
}
```

**Note:** `limit` and `columns` are TOP-LEVEL params, not inside `filters[]`.

---

## Using Entity IDs from Context

When prior steps or turns have loaded entities, reference them by ID:

**Fetch specific entities:**
```json
{
  "table": "recipes",
  "filters": [
    {"field": "id", "op": "in", "value": ["recipe_1", "recipe_2"]}
  ]
}
```

**Exclude specific entities:**
```json
{
  "table": "recipes",
  "filters": [
    {"field": "id", "op": "not_in", "value": ["recipe_5", "recipe_6"]}
  ]
}
```

---

## Advanced Patterns

### Semantic Search (Recipes only)

Find recipes by intent, not keywords:
```json
{
  "table": "recipes",
  "filters": [
    {"field": "_semantic", "op": "similar", "value": "quick weeknight dinner"}
  ]
}
```
**Note:** Only works for `recipes` table. Uses embeddings for conceptual matching.

### OR Logic

Use `or_filters` (top-level param) for multiple keywords:
```json
{
  "table": "recipes",
  "or_filters": [
    {"field": "name", "op": "ilike", "value": "%chicken%"},
    {"field": "name", "op": "ilike", "value": "%rice%"}
  ]
}
```

### Date Range

```json
{
  "table": "meal_plans",
  "filters": [
    {"field": "date", "op": ">=", "value": "2026-01-01"},
    {"field": "date", "op": "<=", "value": "2026-01-07"}
  ]
}
```

### Array Contains

```json
{"field": "occasions", "op": "contains", "value": ["weeknight"]}
```

**Note:** `tags` field is NOT reliably queryable — use semantic search or read all and analyze instead.

### Column Selection

If selecting specific columns:
- **Always include `id`** — required for entity tracking
- **Always include `name` or `title`** — for readability

```json
{"columns": ["id", "name", "instructions"]}
```

**Prefer omitting `columns` entirely** to get all fields.

---

## Principles

1. **Check context first.** Data from prior steps may already be available.

2. **One query often enough.** Get what you need and complete.

3. **Empty = Valid.** 0 results is an answer. Complete the step with that fact.

4. **Limit wisely.** Use `limit` to avoid fetching too much data.

5. **Include names.** When selecting specific columns, always include `name` or `title`.

6. **Match step intent for depth.** For recipes: only fetch `instructions` field if step explicitly needs it (e.g., "with instructions", "full recipe"). Otherwise save tokens.
