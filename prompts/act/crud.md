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

**Supported Operators:**

| Operator | Purpose | Example |
|----------|---------|---------|
| `=` | Exact match | `{"field": "id", "op": "=", "value": "recipe_1"}` |
| `!=` | Not equal | `{"field": "status", "op": "!=", "value": "expired"}` |
| `>`, `<`, `>=`, `<=` | Comparisons | `{"field": "quantity", "op": ">", "value": 0}` |
| `in` | Match any in list | `{"field": "id", "op": "in", "value": ["recipe_1", "recipe_2"]}` |
| `not_in` | Exclude list | `{"field": "id", "op": "not_in", "value": ["recipe_5"]}` |
| `ilike` | Fuzzy text (case-insensitive) | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Field is null | `{"field": "deleted_at", "op": "is_null", "value": true}` |
| `is_not_null` | Field has value | `{"field": "instructions", "op": "is_not_null", "value": true}` |
| `contains` | Array contains | `{"field": "tags", "op": "contains", "value": ["quick"]}` |
| `similar` | Semantic search | `{"field": "_semantic", "op": "similar", "value": "light summer dinner"}` |

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
**Note:** Use simple refs like `recipe_1`, `inv_5`. The system translates automatically.

### Fuzzy Search
```json
{"field": "name", "op": "ilike", "value": "%chicken%"}
```

### Semantic Search (Recipes)
Find recipes by intent, not keywords:
```json
{
  "table": "recipes",
  "filters": [
    {"field": "_semantic", "op": "similar", "value": "quick weeknight dinner with vegetables"}
  ]
}
```
**Note:** Only works for `recipes` table. Uses embeddings to find conceptually similar recipes.

### OR Logic (multiple keywords)
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
{"field": "occasions", "op": "contains", "value": ["weeknight"]}
```

---

## Exclusion Pattern

When you need to exclude specific items (e.g., user said "no cod"):

**Use `not_in` on IDs:**
```json
{
  "table": "recipes",
  "filters": [
    {"field": "id", "op": "not_in", "value": ["recipe_5", "recipe_6"]}
  ]
}
```

**For single exclusion, use `!=`:**
```json
{"field": "id", "op": "!=", "value": "recipe_5"}
```

**When excluding by attribute** (e.g., exclude all fish recipes):
1. First identify items to exclude via read or analyze
2. Then use `not_in` with the identified IDs

---

## Column Selection

If selecting specific columns, **always include `name` or `title`** for readability:
```json
{"columns": ["id", "name", "instructions"]}
```

---

## Schema = Your Tables

Only access tables shown in the schema section. Query results are facts — 0 records means those items don't exist.
