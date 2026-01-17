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

**Operators:**

| Operator | Purpose | Example |
|----------|---------|---------|
| `=` | Exact match | `{"field": "id", "op": "=", "value": "recipe_1"}` |
| `!=` | Not equal | `{"field": "status", "op": "!=", "value": "expired"}` |
| `>`, `<`, `>=`, `<=` | Comparisons | `{"field": "quantity", "op": ">", "value": 0}` |
| `in` | Match any in list | `{"field": "id", "op": "in", "value": ["recipe_1", "recipe_2"]}` |
| `not_in` | Exclude list | `{"field": "id", "op": "not_in", "value": ["recipe_5"]}` |
| `ilike` | Fuzzy text | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Field is null | `{"field": "expiry_date", "op": "is_null", "value": true}` |
| `contains` | Array contains | `{"field": "occasions", "op": "contains", "value": ["weeknight"]}` |

**Note:** Use simple refs like `recipe_1`, `inv_5`. System translates to UUIDs automatically.

---

## Schema = Your Tables

Only access tables shown in the schema section. Query results are facts — 0 records means empty.
