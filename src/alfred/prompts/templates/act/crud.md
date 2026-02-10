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
| `=` | Exact match | `{"field": "id", "op": "=", "value": "item_1"}` |
| `!=` | Not equal | `{"field": "status", "op": "!=", "value": "expired"}` |
| `>`, `<`, `>=`, `<=` | Comparisons | `{"field": "quantity", "op": ">", "value": 0}` |
| `in` | Match any in list | `{"field": "id", "op": "in", "value": ["item_1", "item_2"]}` |
| `not_in` | Exclude list | `{"field": "id", "op": "not_in", "value": ["item_5"]}` |
| `ilike` | Fuzzy text | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Field is null | `{"field": "due_date", "op": "is_null", "value": true}` |
| `contains` | Array contains | `{"field": "occasions", "op": "contains", "value": ["weeknight"]}` |

**Note:** Use simple refs like `item_1`, `item_5`. System translates to UUIDs automatically.

---

## Schema = Your Tables

Only access tables shown in the schema section. Query results are facts — 0 records means empty.
