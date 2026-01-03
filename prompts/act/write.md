# Act - WRITE Step Mechanics

## Purpose

Create, update, or delete database records.

---

## How to Execute

1. Read the step description — know what to write
2. Check "Previous Step Note" for IDs needed as FK references
3. Make CRUD calls (`db_create`, `db_update`, `db_delete`)
4. Tag any new entities created
5. `step_complete` with summary of what was created/modified

---

## Tool Selection

| Goal | Tool |
|------|------|
| Create new record(s) | `db_create` |
| Modify existing | `db_update` |
| Remove record(s) | `db_delete` |

---

## Batch Operations

When creating/updating/deleting MULTIPLE items:

**⚠️ CRITICAL: Complete ALL items before `step_complete`**

If the step says "Save 3 recipes with ingredients":
1. `db_create` on parent table (batch) → get N IDs
2. `db_create` children for item 1
3. `db_create` children for item 2
4. `db_create` children for item 3
5. `step_complete` (only NOW)

**Do NOT call `step_complete` after handling only SOME of a batch.**

---

## Linked Tables Pattern

When tables are linked (parent ↔ children):

### CREATE Order: Parent → Children
```
1. Create parent record → get ID
2. Create child records with parent's ID as FK
```

### DELETE Order: Children → Parent
```
1. Delete child records first (by parent FK)
2. Delete parent record
```

### UPDATE: Depends on Scope
- Metadata only: Just update parent
- Replace children: Delete old children, create new ones

---

## FK Handling

When creating records that reference other tables:
- Use IDs from "Previous Step Note" or "Entity IDs from Prior Steps"
- Use actual UUIDs only — never use temp_ids for FK columns
- If FK is optional and not available, use `null` (not empty string)

---

## Entity Tagging

When creating records, report them for tracking:

```json
{
  "action": "step_complete",
  "result_summary": "Created 3 recipes with ingredients",
  "data": {...},
  "new_entities": [
    {"id": "uuid-1", "type": "recipe", "label": "Butter Chicken"},
    {"id": "uuid-2", "type": "recipe", "label": "Garlic Pasta"}
  ]
}
```

---

## Ingredient Names (for recipe_ingredients, inventory, shopping_list)

Use **simple, canonical names** that match grocery items:
- ✅ "chickpeas", "chicken thighs", "olive oil"
- ❌ "crispy roasted chickpeas", "herby greens mix"

---

## What NOT to do

- Use temp_ids as FK values in db_create
- Complete after handling only SOME of a batch
- Forget linked table operations (e.g., create recipe without ingredients)
- Skip the `note_for_next_step` with new IDs
- Use prepared dish names as ingredient names
