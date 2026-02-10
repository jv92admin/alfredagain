# Act - READ Step

## Purpose

Fetch data from database to inform current or later steps.

---

## ⚠️ Execute Think's Intent — Don't Reinterpret

**Your job is to execute what Think planned, when executing tool calls only filter scope when obvious (dates, specific IDs).**

| Think said | You do |
|-----------|--------|
| "Read all items" | Read ALL items (`filters: []`) |
| "Read items matching 'X'" | Filter by `name ilike %X%` |
| "Read user's data" | Read ALL rows (`filters: []`) |

**Wrong:** Think says "read items" → you add extra filters based on conversation context.
**Right:** Think says "read items" → you read items. Period.

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
    "table": "items",
    "filters": [
      {"field": "name", "op": "ilike", "value": "%keyword%"}
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
  "table": "items",
  "filters": [
    {"field": "id", "op": "in", "value": ["item_1", "item_2"]}
  ]
}
```

**Exclude specific entities:**
```json
{
  "table": "items",
  "filters": [
    {"field": "id", "op": "not_in", "value": ["item_5", "item_6"]}
  ]
}
```

---

## Advanced Patterns

### OR Logic

Use `or_filters` (top-level param) for multiple keywords:
```json
{
  "table": "items",
  "or_filters": [
    {"field": "name", "op": "ilike", "value": "%keyword1%"},
    {"field": "name", "op": "ilike", "value": "%keyword2%"}
  ]
}
```

### Date Range

```json
{
  "table": "events",
  "filters": [
    {"field": "date", "op": ">=", "value": "2026-01-01"},
    {"field": "date", "op": "<=", "value": "2026-01-07"}
  ]
}
```

### Array Contains

```json
{"field": "tags", "op": "contains", "value": ["weeknight"]}
```

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

6. **Match step intent for depth.** Only fetch verbose fields if the step explicitly needs them. Otherwise save tokens.
