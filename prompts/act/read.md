# Act - READ Step

## Purpose

Fetch data from database to inform current or later steps.

---

## Before You Query

**Check Entity Context first.** If the data you need is already in the Entity Context section (from a prior step or turn), use it directly instead of re-reading.

- `recipe_1`, `recipe_2` already loaded? → Reference them, skip the read
- Need a specific field not in context? → Read with `columns` for just that field
- Need fresh data (e.g., checking for updates)? → Read is appropriate

---

## How to Execute

1. Read the step description — that's your query scope
2. **Check Entity Context** — is the data already available?
3. Check "Previous Step Note" for IDs to filter by
4. Build filters based on what's asked
5. Call `db_read` with appropriate table and filters
6. `step_complete` with results (even if empty)

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

## Principles

1. **Check context first.** Data from prior steps may already be available.

2. **One query often enough.** Get what you need and complete.

3. **Empty = Valid.** 0 results is an answer. Complete the step with that fact.

4. **Limit wisely.** Use `limit` to avoid fetching too much data.

5. **Include names.** When selecting specific columns, always include `name` or `title`.

6. **Match step intent for depth.** For recipes: only fetch `instructions` field if step explicitly needs it (e.g., "with instructions", "full recipe"). Otherwise save tokens.
