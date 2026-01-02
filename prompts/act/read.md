# Act - READ Step Mechanics

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

## Complete db_read Example

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

**Note:** `limit` is a TOP-LEVEL param, NOT inside `filters[]`.

---

## Filter Patterns

Each filter is an object: `{"field": "...", "op": "...", "value": "..."}`

### Exact Match
```json
{"field": "id", "op": "=", "value": "uuid-here"}
```

### Fuzzy Search (names, descriptions)
```json
{"field": "name", "op": "ilike", "value": "%chicken%"}
```

### Multiple Keywords (OR logic)
Use `or_filters` (top-level param, same level as `filters`):
```json
{
  "table": "recipes",
  "or_filters": [
    {"field": "name", "op": "ilike", "value": "%chicken%"},
    {"field": "name", "op": "ilike", "value": "%rice%"}
  ],
  "limit": 10
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

### Array Contains (tags, etc.)
```json
{"field": "tags", "op": "contains", "value": ["weekday"]}
```

---

## Principles

1. **One query often enough.** Don't over-query. Get what you need and complete.

2. **Empty = Valid.** 0 results is an answer. Complete the step with that fact.

3. **Don't retry empty.** Same filter won't give different results. Move on.

4. **Limit wisely.** Use `limit` to avoid fetching too much data.

---

## What NOT to do

- Re-query the same table hoping for different results
- Query without filters when the step asks for specific items
- Forget to complete the step after getting results
- Put `limit` or `columns` inside `filters[]` — they're top-level params
