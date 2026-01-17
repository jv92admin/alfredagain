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
    "table": "recipe_ingredients",
    "data": [
      {"recipe_id": "gen_recipe_1", "name": "garlic", "quantity": 2, "unit": "cloves"},
      {"recipe_id": "gen_recipe_1", "name": "olive oil", "quantity": 2, "unit": "tbsp"},
      {"recipe_id": "gen_recipe_2", "name": "chicken", "quantity": 1, "unit": "lb"},
      {"recipe_id": "gen_recipe_2", "name": "rice", "quantity": 1, "unit": "cup"}
    ]
  }
}
```

**Key:** Include ALL records for ALL items in one call. Don't do recipe 1's ingredients, then recipe 2's separately.

---

## Update

Modify existing record by ID:
```json
{
  "tool": "db_update",
  "params": {
    "table": "shopping_list",
    "filters": [{"field": "id", "op": "=", "value": "shop_1"}],
    "data": {"is_purchased": true}
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
    "table": "inventory",
    "filters": [{"field": "id", "op": "=", "value": "inv_5"}]
  }
}
```

**Note:** Subdomain-specific patterns (e.g., linked tables, cascades) are in the Schema section below.

---

## Linked Tables (Parent → Children)

When creating parent + children:
1. `db_create` parent(s) → get IDs
2. `db_create` ALL children in one batch with parent IDs

When deleting:
- `recipes` → `recipe_ingredients`: **CASCADE** (just delete recipes)
- Other tables: delete children first, then parent

---

## FK Handling

- Use refs from "Working Set" or "Previous Step Note": `recipe_1`, `gen_recipe_1`
- System translates refs to UUIDs automatically
- If FK is optional and unavailable, use `null`

---

## Ingredient Names (for recipe_ingredients)

Use **simple, canonical names** in the `name` field:
- ✅ "chickpeas", "chicken thigh", "olive oil", "garlic", "basil"
- ❌ "crispy roasted chickpeas", "Trader Joe's organic olive oil"

**Why:** The system auto-links ingredients to a canonical database via `ingredient_id`. Simple names match better.

**Qualifiers go in `notes`:**
```json
{"name": "garlic", "quantity": 2, "unit": "cloves", "notes": "minced"}
{"name": "basil", "quantity": 1, "unit": "cup", "notes": "fresh, loosely packed"}
```

**Singular forms preferred:** "chicken thigh" not "chicken thighs" (quantity handles plural)

---

## Before `step_complete`

Ask yourself:
1. Does everything in "Content to Save" now exist in the database?
2. Did I handle ALL items, not just some?

If no → make more tool calls
If yes → `step_complete` with `note_for_next_step` containing new IDs
