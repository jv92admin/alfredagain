# Act Context Injection Audit

**Date:** 2026-01-16
**Status:** RESOLVED

## Summary

This audit traces how context flows into Act prompts, identifies issues with recipe ingredient updates, and documents bloat in the current prompt structure.

---

## Issues Identified

### Issue 1: Wrong Guidance in `examples.py`

**File:** `src/alfred/prompts/examples.py` lines 77-83

**Problem:** The recipe update pattern says delete+create for ingredient changes:
```python
examples.append("""**Update Recipe Pattern:**
- **Metadata only** (name, tags, description): Just `db_update` on recipes
- **Replace ingredients**: 
  1. `db_delete` on `recipe_ingredients` WHERE recipe_id = X
  2. `db_create` new ingredients with same recipe_id
- **Add ingredient**: Just `db_create` on recipe_ingredients""")
```

**Correct Pattern:** (from `personas.py` which is NOT being used for this):
```python
### Ingredient Updates (`recipe_ingredients` table)
| Change | Tool | Example |
|--------|------|---------|
| Swap ingredient | `db_update` | `{"data": {"name": "frozen broccoli"}}` |
| Change qty/unit | `db_update` | `{"data": {"quantity": 3, "unit": "cloves"}}` |
```

**Root Cause:** `examples.py` was written with a bulk-replacement mental model. Since `recipe_ingredients` has its own `id` column, we should use `db_update` by row ID.

**Fix:** Update `examples.py` to use correct `db_update` pattern.

---

### Issue 2: Ingredient IDs Not Shown With Recipe in Entity Context

**File:** `src/alfred/graph/nodes/act.py` function `_format_recipe_data()` lines 1020-1035

**Problem:** Recipe entity context shows ingredients as formatted strings without refs:
```markdown
### `recipe_1`: Thai Chicken Pad See Ew
  **ingredients (8 items):**
    - 1 cup Chinese broccoli (gai lan)   ← NO ID!
    - 1 lb chicken thighs                ← NO ID!
```

Meanwhile ingredient refs appear SEPARATELY in "Recent Context (refs only)":
```markdown
## Recent Context (refs only)
- `ri_1`: Chinese broccoli (gai lan) (ri) [read]
```

**Why This Happens:**
1. Ingredients are registered as separate entities in SessionIdRegistry
2. `_format_recipe_data()` doesn't include refs when formatting
3. Act has to mentally connect "Chinese broccoli" to `ri_1` across two sections

**Code Location:**
```python
# Lines 1024-1030 in act.py
for ing in ingredients:
    qty = ing.get("quantity", "")
    unit = ing.get("unit", "")
    name = ing.get("name", "?")
    qty_str = f"{qty} {unit} " if qty else ""
    lines.append(f"    - {qty_str}{name}")  # ← NO REF!
```

**Fix:** Include ingredient ref when formatting:
```python
# Get ref from registry
ref = ing.get("_ref") or f"ri_{idx}"
lines.append(f"    - `{ref}`: {qty_str}{name}")
```

---

### Issue 3: Ingredients Split From Recipe in Context

**Problem:** Recipe is in "Active Entities", its ingredients are in "Recent Context (refs only)" as separate entries.

**Why:** SessionIdRegistry tracks all entities independently. When Act formats context:
1. Recipe goes in "Active Entities" (with full data)
2. Recipe_ingredients go in "Recent Context" (as refs only, separate from recipe)

**Fix Options:**
1. **Inline refs:** Show ingredient refs within the recipe entity context (Issue 2 fix)
2. **Grouping:** Note in "Recent Context" that these belong to recipe_1
3. **Structural:** Have Act's entity context builder group related entities

---

### Issue 4: `note_for_next_step` Not Appearing in Prompts

**Observation:** Step 9 completed with:
```json
"note_for_next_step": "recipe_1 full details loaded"
```

But step 14 (next turn's first step) has no "## Previous Step Note" section.

**Analysis:**
- `prev_step_note` is designed for step-to-step continuity WITHIN a turn
- When a new turn starts (step 14), there are no "previous steps" in THIS turn yet
- The note from turn 2's last step doesn't carry into turn 3

**Behavior:** Working as designed, but confusing because:
1. Guidance references "Previous Step Note"
2. Single-step turns never have a previous step
3. The note exists in state but doesn't apply

**Fix:** Could be clearer about scope (within-turn only) in guidance.

---

### Issue 5: Act Identity Section Bloat

**Location:** `prompts/system.md` (shared) + `prompts/act/*.md` files

**Current State (from prompt log):**
- Lines 17-61: Generic Alfred identity (~500 tokens)
- Lines 65-181: Core identity + CRUD reference (~1200 tokens)

**Problems:**
1. Generic identity (warm, helpful, what you can do) is wasteful for Act
2. CRUD tools reference repeated in every call
3. No explanation of WHY tables exist or how they relate

**Observation:** We could:
1. Trim generic identity for Act (it's an execution layer, not user-facing)
2. Move detailed CRUD to schema injection (subdomain-specific)
3. Invest saved tokens in better subdomain education

---

### Issue 6: Schema Section is "What" Without "Why"

**Current:**
```markdown
## Available Tables (subdomain: recipes)
### recipes
| Column | Type | Nullable |
...
### recipe_ingredients (REQUIRED for each recipe!)
```

**Missing:**
- WHY these are separate tables
- HOW they coordinate for updates
- WHEN to use which operation

**Needed:**
```markdown
## Recipes Data Model

**Why Separate Tables:**
- `recipes` = core recipe metadata + instructions  
- `recipe_ingredients` = individual ingredient rows with their own IDs

**Coordinating Updates:**
- To update recipe metadata: `db_update` on `recipes`
- To update an ingredient: `db_update` on `recipe_ingredients` by row ID
- To add ingredient: `db_create` on `recipe_ingredients`
- To remove ingredient: `db_delete` on `recipe_ingredients` by row ID
- To delete recipe: `db_delete` on `recipes` (ingredients CASCADE)
```

---

## Context Injection Flow (Reference)

### How Entity Context Reaches Act

1. **SessionIdRegistry** stores all known entity refs and their data
2. **`act.py:_build_enhanced_entity_context()`** formats entities for prompt
3. For recipes, **`_format_recipe_data()`** is called
4. Ingredients are formatted WITHOUT their refs (Issue 2)

### How Schema Reaches Act

1. **`get_schema_for_subdomain()`** in `tools/schema.py` builds schema
2. **`get_contextual_examples()`** in `prompts/examples.py` adds patterns
3. For recipe writes, the WRONG pattern is injected (Issue 1)

### How Ingredient IDs Get Registered

1. When recipe is read with `recipe_ingredients(id, name, ...)` 
2. The ingredients are returned nested in the recipe response
3. **`_register_linked_records()`** creates refs like `ri_1`, `ri_2`
4. These refs go into SessionIdRegistry
5. But when formatting recipe for context, we don't include them!

---

## Fixes Applied

| Priority | Issue | Fix | Status |
|----------|-------|-----|--------|
| **P0** | #1 Wrong examples.py guidance | Changed delete+create to db_update by ID | ✅ DONE |
| **P1** | #2 Ingredient IDs not shown | Modified `_format_recipe_data()` to include refs | ✅ DONE |
| **P1** | #6 Schema lacks "why" | Added relationship explanation to schema section | ✅ DONE |
| **P2** | #5 Act identity bloat | Removed system.md from Act (execution layer) | ✅ DONE |
| **P3** | #3 Split context | Addressed via #2 (inline refs) | ✅ DONE |
| **P4** | #4 Note scope unclear | By design (within-turn only) | N/A |

---

## Changes Made

### 1. `src/alfred/prompts/examples.py`
- Fixed recipe update pattern: now says `db_update` by row ID, not delete+create

### 2. `src/alfred/graph/nodes/act.py`
- `_format_recipe_data()` now accepts registry and shows ingredient refs inline
- Removed `system.md` from Act system prompt (Act is execution, not user-facing)

### 3. `src/alfred/tools/schema.py`
- Updated recipes schema section with clear data model explanation
- Added table showing all operations (CREATE, DELETE, UPDATE, ADD, REMOVE)
- Removed dead code (duplicate `get_contextual_examples` function)

---

## Testing

Test with recipe ingredient update scenario:
1. "Show me my pad see ew recipe"
2. "Change the gai lan to broccoli"

Expected:
- Think plans read + write steps
- Act shows ingredient refs inline with recipe (e.g., `ri_1`: Chinese broccoli)
- Act uses `db_update` on `recipe_ingredients` by row ID
- Reply reports actual changes made
