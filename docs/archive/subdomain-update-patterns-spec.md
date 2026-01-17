# Subdomain Update Patterns Specification

**Date:** 2026-01-15  
**Status:** Draft  
**Problem:** Recipe ingredient swap wasn't persisted — system updated instruction text but not `recipe_ingredients` table

---

## Executive Summary

When users request changes to entities with linked tables (e.g., recipes with ingredients), Think must decompose the update into appropriate steps. Currently, Think plans vague "update recipe" steps that Act interprets as metadata-only updates, missing linked table operations.

**Solution:** Introduce **Mutation Type Classification** so Think explicitly plans the correct operations for each type of change.

---

## 1. Problem Analysis

### The Failed Recipe Update

**User Request:**
> "can i just use frozen broccoli this time? and can we add a chef tip that notes this sub? i dont think im buying gai lan often? so we can make brocolli the default and the gai lan as an elevated tip?"

**What Think Planned:**
```json
{
  "steps": [
    {"description": "Read full details for recipe_1", "step_type": "read"},
    {"description": "Update recipe to use frozen broccoli as default vegetable, add chef tip", "step_type": "write"}
  ]
}
```

**What Act Did:**
- `db_update` on `recipes` table: Updated `instructions` array text
- Did NOT touch `recipe_ingredients` table

**What Should Have Happened:**
1. `db_delete` on `recipe_ingredients` WHERE name ILIKE '%gai lan%' AND recipe_id = recipe_1
2. `db_create` on `recipe_ingredients` with name: "frozen broccoli"
3. `db_update` on `recipes` to update instructions text with chef tip

### Root Cause

Neither Think nor Act has a system to classify **what kind of update** this is:

| Mutation Type | Tables Affected | Example |
|--------------|-----------------|---------|
| Metadata-only | `recipes` | Change name, description, tags |
| Instructions-only | `recipes` | Reword a step, add chef tip |
| **Ingredient swap** | `recipe_ingredients` | Replace gai lan → broccoli |
| **Ingredient add/remove** | `recipe_ingredients` | Add optional garnish |
| Full replacement | `recipes` + `recipe_ingredients` | Major recipe overhaul |

The step description "Update recipe to use frozen broccoli" was ambiguous. Act defaulted to the simplest interpretation (instructions text).

---

## 2. Subdomain Linked Table Map

### Tables with Linked Children

| Subdomain | Parent Table | Child Table | FK | Cascade? |
|-----------|-------------|-------------|-----|----------|
| **recipes** | `recipes` | `recipe_ingredients` | recipe_id | DELETE only |
| **preferences** | `preferences` | `flavor_preferences` | user_id | DELETE only |

### Tables with FK References (Not Children)

| Subdomain | Table | References | FK |
|-----------|-------|------------|-----|
| **meal_plans** | `meal_plans` | `recipes` | recipe_id |
| **inventory** | `inventory` | `ingredients` | ingredient_id |
| **shopping** | `shopping_list` | `ingredients` | ingredient_id |
| **tasks** | `tasks` | `meal_plans`, `recipes` | meal_plan_id, recipe_id |

---

## 3. Mutation Type Classification

### Recipe Subdomain

| Mutation Type | Signal Words | Tables | Operations |
|--------------|--------------|--------|------------|
| **metadata** | "rename", "change description", "update tags" | recipes | `db_update` |
| **instructions** | "reword", "add tip", "modify step" | recipes | `db_update` |
| **ingredient_swap** | "swap X for Y", "use X instead of Y", "replace X with Y" | recipe_ingredients | `db_delete` old → `db_create` new |
| **ingredient_add** | "add X", "include X" | recipe_ingredients | `db_create` |
| **ingredient_remove** | "remove X", "take out X" | recipe_ingredients | `db_delete` |
| **full_replacement** | "completely redo", "overhaul" | recipes + recipe_ingredients | Complex multi-step |

### Inventory Subdomain

| Mutation Type | Signal Words | Tables | Operations |
|--------------|--------------|--------|------------|
| **quantity** | "update quantity", "change amount", "used some" | inventory | `db_update` |
| **metadata** | "move to fridge", "change location" | inventory | `db_update` |
| **consolidate** | "combine", "merge" | inventory | `db_update` (sum quantities) or `db_delete` + `db_update` |

### Meal Plans Subdomain

| Mutation Type | Signal Words | Tables | Operations |
|--------------|--------------|--------|------------|
| **recipe_change** | "use different recipe", "swap recipe" | meal_plans | `db_update` (recipe_id) |
| **schedule_change** | "move to Tuesday", "change date" | meal_plans | `db_update` (date) |
| **notes_change** | "add note", "update servings" | meal_plans | `db_update` |

### Shopping Subdomain

| Mutation Type | Signal Words | Tables | Operations |
|--------------|--------------|--------|------------|
| **quantity** | "need more", "change amount" | shopping_list | `db_update` |
| **purchase** | "bought it", "purchased", "mark done" | shopping_list | `db_update` (is_purchased) |

### Preferences Subdomain

| Mutation Type | Signal Words | Tables | Operations |
|--------------|--------------|--------|------------|
| **add_restriction** | "add allergy", "now vegetarian" | preferences | `db_update` (array append) |
| **remove_restriction** | "no longer allergic", "can eat X now" | preferences | `db_update` (array remove) |
| **update_setting** | "change skill level", "update household size" | preferences | `db_update` |

---

## 4. Think Guidance (Step Decomposition)

### Proposed Addition to Think Prompt

```markdown
### Mutation Types for Linked Tables

When planning WRITE steps, identify the **mutation type** to ensure correct operations:

**Recipe Updates:**

| User Says | Mutation Type | Steps Needed |
|-----------|---------------|--------------|
| "rename to X", "change description" | metadata | 1 write step (recipes table) |
| "add a chef tip", "modify step 3" | instructions | 1 write step (recipes table) |
| "swap gai lan for broccoli" | **ingredient_swap** | 2-3 write steps (delete old → create new → maybe update instructions) |
| "add garlic as optional" | ingredient_add | 1 write step (recipe_ingredients table) |
| "remove the cilantro" | ingredient_remove | 1 write step (recipe_ingredients table) |

**How to plan ingredient changes:**

```json
// WRONG - Ambiguous
{"description": "Update recipe to use broccoli", "step_type": "write", "subdomain": "recipes"}

// CORRECT - Explicit
{"steps": [
  {"description": "Delete gai lan ingredient from recipe_1", "step_type": "write", "subdomain": "recipes"},
  {"description": "Add frozen broccoli ingredient to recipe_1", "step_type": "write", "subdomain": "recipes"},
  {"description": "Update recipe instructions to mention broccoli + gai lan tip", "step_type": "write", "subdomain": "recipes"}
]}
```

**Key insight:** An ingredient swap is NOT a metadata update. It requires operations on `recipe_ingredients` table.
```

---

## 5. Act Guidance (Operation Detection)

### Proposed Addition to Act Write Prompt

```markdown
### Detecting Mutation Type

Before executing, classify what kind of update this is:

**Step description signals:**

| If step says... | Mutation type | You do... |
|-----------------|---------------|-----------|
| "rename", "change name/description/tags" | metadata | `db_update` on `recipes` |
| "add tip", "modify instruction", "reword step" | instructions | `db_update` on `recipes` |
| "delete ingredient X", "remove X from recipe" | ingredient_remove | `db_delete` on `recipe_ingredients` |
| "add ingredient X", "include X in recipe" | ingredient_add | `db_create` on `recipe_ingredients` |
| "swap X for Y", "replace X with Y" | ingredient_swap | `db_delete` old + `db_create` new on `recipe_ingredients` |

**⚠️ Common Mistake:**
"Update recipe to use broccoli instead of gai lan" is an **ingredient swap**, not a metadata update.
- ❌ `db_update` on `recipes` (only changes text)
- ✅ `db_delete` on `recipe_ingredients` (remove gai lan)
- ✅ `db_create` on `recipe_ingredients` (add broccoli)

**If step is ambiguous:**
Call `blocked` with `reason_code: "AMBIGUOUS_MUTATION"` and request clarification.
```

---

## 6. Implementation Options

### Option A: Enhanced Prompt Guidance (Minimal Code)

Add the above guidance to:
1. `prompts/think.md` — Mutation type classification in `<system_structure>`
2. `prompts/act/write.md` — Operation detection guidance
3. `src/alfred/prompts/personas.py` — Update SUBDOMAIN_INTRO for recipes

**Pros:** Low code change, fast to implement  
**Cons:** Still relies on LLM interpretation

### Option B: Step Type Extension (Medium Code)

Extend step types to include mutation hints:

```python
class Step(BaseModel):
    description: str
    step_type: Literal["read", "write", "analyze", "generate"]
    subdomain: str
    # NEW: Optional mutation hint for write steps
    mutation_type: Literal["metadata", "instructions", "ingredient_swap", "ingredient_add", "ingredient_remove", "full_replacement"] | None = None
```

Think explicitly sets `mutation_type` when planning writes. Act uses this to determine operations.

**Pros:** Explicit, less ambiguity  
**Cons:** Requires Think to learn new field, more complex

### Option C: Declarative Update API (High Code)

Create high-level update functions that handle linked tables automatically:

```python
async def update_recipe(
    recipe_id: str,
    changes: RecipeChanges,  # Pydantic model
    user_id: str
) -> dict:
    """
    Declarative recipe update. System handles table operations.
    """
    # If ingredients changed
    if changes.ingredients:
        for ingredient_change in changes.ingredients:
            if ingredient_change.action == "remove":
                await db_delete(...)
            elif ingredient_change.action == "add":
                await db_create(...)
            elif ingredient_change.action == "swap":
                await db_delete(...)
                await db_create(...)
    
    # If metadata changed
    if changes.metadata:
        await db_update(...)
    
    return updated_recipe
```

**Pros:** Deterministic, LLM just describes intent  
**Cons:** Significant code change, new API surface

---

## 7. Recommended Approach

**Phase 1: Enhanced Prompt Guidance (Immediate)**
- Update Think prompt with mutation type classification
- Update Act write guidance with operation detection
- Update SUBDOMAIN_INTRO for recipes with explicit patterns

**Phase 2: Step Type Extension (Short-term)**
- Add optional `mutation_type` field to steps
- Think sets it for write steps involving linked tables
- Act uses it as directive (not just hint)

**Phase 3: Declarative API (Long-term consideration)**
- If Phase 1-2 still show errors, build deterministic layer
- LLM describes "what should change", system executes

---

## 8. Success Metrics

After implementation, the following should work correctly:

| User Request | Expected Behavior |
|-------------|-------------------|
| "Swap gai lan for broccoli in recipe_1" | `recipe_ingredients` row changes |
| "Add garlic to the ingredients" | New row in `recipe_ingredients` |
| "Remove the optional cilantro" | Row deleted from `recipe_ingredients` |
| "Rename to 'Quick Pad See Ew'" | Only `recipes.name` changes |
| "Add a chef tip about gai lan" | Only `recipes.instructions` changes |

---

## Related Docs

- [recipe-update-findings.md](../audit/recipe-update-findings.md) — Original bug report
- [act-prompt-structure.md](../prompts/act-prompt-structure.md) — Act prompt assembly
- [context-engineering-architecture.md](../context-engineering-architecture.md) — Overall architecture

---

*Last updated: 2026-01-15*
