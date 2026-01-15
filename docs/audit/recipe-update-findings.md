# Recipe Update Findings

**Date:** 2026-01-15  
**Status:** Investigation needed  
**Priority:** Medium

---

## Summary

When user asked to update a recipe to swap ingredients (gai lan → frozen broccoli), the system:
1. ✅ Updated recipe metadata (description, maybe instructions text)
2. ❌ Did NOT update `recipe_ingredients` table
3. ⚠️ Reply presented a "successful" ingredient swap that didn't happen

---

## The Observed Flow

### User Request
> "hmm can i just use frozen broccoli this time? and can we add a chef tip that notes this sub? i dont think im buying gai lan often? so we can make broccoli the default and the gai lan as an elevated tip?"

### What Think Planned
```
Step 1: Read full details for Thai Chicken Pad See Ew recipe (recipe_1)
Step 2: Update recipe to use frozen broccoli as default vegetable, add chef tip...
```

### What Act Did
- Step 1: `db_read` on recipes table ✅
- Step 2: `db_update` on recipes table (metadata only) ✅
  - Updated 1 record
  - Did NOT touch `recipe_ingredients` table

### What Reply Said
> "I've updated your Thai Chicken Pad See Ew recipe to use frozen broccoli as the default vegetable..."
> 
> **Ingredients:**
> - Frozen broccoli (default) ← **NOT IN DATABASE**

---

## Root Cause Analysis

### Issue 1: Think didn't plan ingredient update steps

The guidance in Act's prompt shows the correct pattern:

```
**Update Recipe Pattern:**
- **Metadata only** (name, tags, description): Just `db_update` on recipes
- **Replace ingredients**: 
  1. `db_delete` on `recipe_ingredients` WHERE recipe_id = X
  2. `db_create` new ingredients with same recipe_id
```

But Think didn't break down "swap ingredient" into explicit linked-table operations.

### Issue 2: Act interpreted "use broccoli" as metadata

Act saw the step description and decided `db_update` on `recipes` was sufficient. It didn't recognize that ingredient changes require `recipe_ingredients` operations.

### Issue 3: Reply trusted goal over evidence

Reply's Execution Summary showed:
```
Type: write (SAVED TO DATABASE) | Subdomain: recipes
Outcome: ✅ SAVED 1 recipes
```

But Reply presented a full ingredient swap based on the **goal**, not the **actual execution**.

---

## Investigation Areas

### 1. Update as a Declarative Function

**Idea:** Make "update" a high-level operation that takes before/after state.

```python
# User intent
update_recipe(
    recipe_id="recipe_1",
    changes={
        "ingredients": [
            {"remove": "Chinese broccoli (gai lan)"},
            {"add": "frozen broccoli"}
        ],
        "instructions": [
            {"step": 7, "append": "Chef's tip: Use gai lan for elevated version"}
        ]
    }
)
```

**System handles deterministically:**
- Diff detection
- Delete old ingredient records
- Create new ingredient records
- Update instructions array

**Benefits:**
- LLM describes intent, system executes correctly
- No reliance on LLM understanding linked tables
- Deterministic, auditable

### 2. Think's Understanding of Linked Tables

**Question:** Does Think know that ingredient changes require `recipe_ingredients` operations?

**Current guidance (in Act prompt):**
```
**Linked Tables:** `recipes` → `recipe_ingredients` (FK cascade)
| Operation | Steps |
| UPDATE (ingredients) | DELETE old ingredients → CREATE new |
```

**Gap:** This guidance is in Act, not Think. Think may not plan the right steps.

**Investigation:**
- [ ] Audit Think prompt for linked table guidance
- [ ] Add explicit "ingredient swap = delete + create" examples to Think
- [ ] Consider adding step planning examples for common mutations

### 3. Reply Accuracy

**Question:** Should Reply validate execution vs goal before presenting?

**Current behavior:** Reply trusts the goal and presents what "should" have happened.

**Options:**
1. Reply validates execution matches goal → surfaces discrepancies
2. Reply strictly presents execution evidence → may confuse user
3. Reply presents both → "I updated the recipe metadata. Note: ingredient list wasn't changed."

**Investigation:**
- [ ] Audit Reply's use of Execution Summary vs Goal
- [ ] Add validation logic or explicit discrepancy surfacing
- [ ] Consider "witness mode" where Reply only reports what happened

---

## Proposed Fixes (Not Implementing Now)

### Short-term
1. Add linked table guidance to Think prompt
2. Add ingredient swap examples to Think
3. Reply validation: check if step_type matches expected outcome

### Medium-term
1. Create `update_recipe()` high-level function
2. Declarative change format (before/after)
3. System handles delete/create deterministically

### Long-term
1. Schema-aware mutation planning
2. Think sees table relationships explicitly
3. Automatic step decomposition for linked operations

---

## Related Docs

- [context_management_findings.md](context_management_findings.md) — Step results persistence
- [act-prompt-structure.md](prompts/act-prompt-structure.md) — Act prompt sections
- [think-prompt-structure.md](prompts/think-prompt-structure.md) — Think prompt sections

---

## One-line Takeaway

**Ingredient updates require `recipe_ingredients` operations, but Think/Act treated it as metadata-only. Reply presented success that didn't happen.**
