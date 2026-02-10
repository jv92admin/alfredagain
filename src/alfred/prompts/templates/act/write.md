# Act - WRITE Step

## Purpose

Create, update, or delete database records.

---

## How to Execute

1. **Check "Content to Save"** — this is your source of truth for what should exist
2. **Check "Previous Step Results"** — what was actually created
3. **Fill the gap** — create/update what's missing
4. **Verify before completing** — does everything in "Content to Save" now exist?

---

## Batch Operations

**Use batch inserts.** One `db_create` call can insert many records:

```json
{
  "tool": "db_create",
  "params": {
    "table": "child_records",
    "data": [
      {"parent_id": "gen_item_1", "name": "item A", "quantity": 2, "unit": "pcs"},
      {"parent_id": "gen_item_1", "name": "item B", "quantity": 1, "unit": "tbsp"},
      {"parent_id": "gen_item_2", "name": "item C", "quantity": 1, "unit": "lb"},
      {"parent_id": "gen_item_2", "name": "item D", "quantity": 1, "unit": "cup"}
    ]
  }
}
```

**Key:** Include ALL records for ALL items in one call. Don't do item 1's children, then item 2's separately.

---

## Update

Modify existing record by ID:
```json
{
  "tool": "db_update",
  "params": {
    "table": "items",
    "filters": [{"field": "id", "op": "=", "value": "item_1"}],
    "data": {"status": "completed"}
  }
}
```

**Pattern:** `filters` targets the record(s), `data` contains fields to change.

---

## Delete

Remove record by ID:
```json
{
  "tool": "db_delete",
  "params": {
    "table": "items",
    "filters": [{"field": "id", "op": "=", "value": "item_5"}]
  }
}
```

**Note:** Subdomain-specific patterns (e.g., linked tables, cascades) are in the Schema section below.

---

## Linked Tables (Parent → Children)

When creating parent + children:
1. `db_create` parent(s) → get IDs
2. `db_create` ALL children in one batch with parent IDs

When deleting, check schema for cascade behavior. Some tables cascade deletes automatically; others require deleting children first.

---

## FK Handling

- Use refs from "Working Set" or "Previous Step Note": `item_1`, `gen_item_1`
- System translates refs to UUIDs automatically
- If FK is optional and unavailable, use `null`

---

## Before `step_complete`

Ask yourself:
1. Does everything in "Content to Save" now exist in the database?
2. Did I handle ALL items, not just some?

If no → make more tool calls
If yes → `step_complete` with `note_for_next_step` containing new IDs
