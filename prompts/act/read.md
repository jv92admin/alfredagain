# Act - READ Step

## Purpose

Fetch data from database to inform current or later steps.

---

## How to Execute

1. Read the step description — that's your query scope
2. Check "Previous Step Note" for IDs to filter by
3. Build filters based on what's asked
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

**Note:** `limit` and `columns` are TOP-LEVEL params, NOT inside `filters[]`.

---

## Principles

1. **One query often enough.** Don't over-query. Get what you need and complete.

2. **Empty = Valid.** 0 results is an answer. Complete the step with that fact.

3. **Don't retry empty.** Same filter won't give different results. Move on.

4. **Limit wisely.** Use `limit` to avoid fetching too much data.

5. **Include names.** When selecting specific columns, always include `name` or `title`.

6. **Match step intent for depth.** For recipes: only fetch `instructions` field if step explicitly needs it (e.g., "with instructions", "full recipe", "show the recipe"). Otherwise save tokens — summary is enough for browsing/planning.

---

## What NOT to do

- Re-query the same table hoping for different results
- Query without filters when the step asks for specific items
- Forget to complete the step after getting results
- Put `limit` or `columns` inside `filters[]` — they're top-level params
