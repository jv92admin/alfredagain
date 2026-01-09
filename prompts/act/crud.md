# CRUD Tools Reference

## Tools

| Tool | Purpose | Params |
|------|---------|--------|
| `db_read` | Fetch rows | `table`, `filters`, `or_filters`, `columns`, `limit` |
| `db_create` | Insert row(s) | `table`, `data` (dict or array of dicts) |
| `db_update` | Modify rows | `table`, `filters`, `data` (dict, applied to ALL matches) |
| `db_delete` | Remove rows | `table`, `filters` |

---

## Filter Syntax

Each filter: `{"field": "...", "op": "...", "value": "..."}`

**Operators:** `=`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `not_in`, `ilike`, `is_null`, `is_not_null`, `contains`

---

## Filter Patterns

### Exact Match
```json
{"field": "id", "op": "=", "value": "recipe_1"}
```

### Multiple IDs (from prior step)
```json
{"field": "id", "op": "in", "value": ["recipe_1", "recipe_2", "recipe_3"]}
```
**Note:** Use simple refs like `recipe_1`, `inv_5`. Never type full UUIDs — the system translates automatically.

### Fuzzy Search
```json
{"field": "name", "op": "ilike", "value": "%chicken%"}
```

### OR Logic (keyword search)
Use `or_filters` (top-level param, same level as `filters`):
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

---

## Column Selection

If selecting specific columns, **always include `name` or `title`** for readability:
```json
{"columns": ["id", "name", "instructions"]}
```

---

## Schema = Your Tables

Only access tables shown in the schema section. Query results are facts — 0 records means those items don't exist.

