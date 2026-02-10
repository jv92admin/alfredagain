# Act Filtering Audit

**Status:** Findings documented  
**Problem:** Act tried `not_ilike` which doesn't exist, causing validation error.

---

## Supported Operators

From `src/alfred/tools/crud.py` line 59:

```python
class FilterClause(BaseModel):
    op: Literal["=", "!=", "neq", ">", "<", ">=", "<=", "in", "not_in", 
                "ilike", "is_null", "is_not_null", "contains", "similar"]
```

### Standard Operators
| Op | Description | Example |
|----|-------------|---------|
| `=` | Exact match | `{"field": "cuisine", "op": "=", "value": "indian"}` |
| `!=`/`neq` | Not equal | `{"field": "status", "op": "!=", "value": "deleted"}` |
| `>`, `<`, `>=`, `<=` | Comparison | `{"field": "prep_time_minutes", "op": "<=", "value": 30}` |
| `in` | Value in list | `{"field": "id", "op": "in", "value": ["recipe_1", "recipe_2"]}` |
| `not_in` | Value not in list | ⚠️ Only works with single value! |
| `ilike` | Case-insensitive LIKE | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Field is null | `{"field": "expiry_date", "op": "is_null", "value": true}` |
| `is_not_null` | Field is not null | `{"field": "parent_recipe_id", "op": "is_not_null", "value": true}` |
| `contains` | Array contains | `{"field": "occasions", "op": "contains", "value": ["weeknight"]}` |
| `similar` | Semantic search | `{"field": "_semantic", "op": "similar", "value": "light dinner"}` |

### NOT Supported
- ❌ `not_ilike` - doesn't exist
- ⚠️ `not_in` with multiple values - degrades to no filter

---

## Smart Behaviors (Hidden from LLM)

### Recipes (`name = "X"`)
```python
# crud.py line 314-322
if params.table == "recipes":
    for i, f in enumerate(filters_to_apply):
        if f.field == "name" and f.op == "=":
            # Convert exact match to fuzzy match
            filters_to_apply[i] = FilterClause(
                field="name",
                op="ilike",
                value=f"%{f.value}%"
            )
```
LLM says `name = "chicken"` → System does `name ilike "%chicken%"`

### Inventory/Shopping (`name = "X"`)
```python
# crud.py line 327-347
if params.table in ("inventory", "shopping_list"):
    from alfred_kitchen.domain.tools.ingredient_lookup import lookup_ingredient
    # ... ingredient lookup logic
```
LLM says `name = "chicken"` → System looks up ingredient, filters by ingredient_id

### Semantic Search (`_semantic`)
```python
# crud.py line 277-292
if semantic_query and params.table in SEMANTIC_SEARCH_TABLES:
    semantic_ids = await _semantic_search_recipes(...)
```
Only works for `recipes` table currently.

---

## The Problem: Exclusions

Act needed to exclude recipes by name but:
1. No `not_ilike` operator exists
2. `not_in` only works with single values
3. Prompt doesn't explain HOW to do exclusions

### What Act Tried (Wrong)
```json
{"field": "name", "op": "not_ilike", "value": "%cod%"}
```
→ Validation error: `not_ilike` not in allowed operators

### What Act Should Have Done
**Option 1: Positive inclusion by ID (best)**
```json
{"field": "id", "op": "in", "value": ["recipe_3", "recipe_4", "recipe_8", "recipe_9"]}
```
Act had recipe_1-9 in Recent Context. User excluded cod (recipe_1, recipe_2, recipe_7), french toast (recipe_5), wings (recipe_6). Remaining: recipe_3, recipe_4, recipe_8, recipe_9.

**Option 2: Read all, filter in analyze step**
Read all recipes, then filter in analyze step: "From the recipes, exclude those with cod, french toast, or wings."

---

## Fix Required

### 1. Add Exclusion Patterns to crud.md

```markdown
### Exclusion Pattern (IMPORTANT)

**There is no `not_ilike` operator.** To exclude items:

1. **If you have IDs in context** — use positive `in` with remaining IDs:
   ```json
   // User wants to exclude recipe_5, recipe_6 from [recipe_1..recipe_9]
   {"field": "id", "op": "in", "value": ["recipe_1", "recipe_2", "recipe_3", "recipe_4", "recipe_7", "recipe_8", "recipe_9"]}
   ```

2. **If you don't have IDs** — read all, then filter in analyze step.

**DO NOT invent operators.** If an operator isn't in the supported list, it won't work.
```

### 2. Update read.md with Context Reuse Guidance

```markdown
## Using Entities from Context

If entities are already in "Recent Context", **don't re-read by name**:

| ❌ Wrong | ✅ Right |
|----------|----------|
| `{"field": "name", "op": "ilike", "value": "%chicken%"}` | `{"field": "id", "op": "in", "value": ["recipe_4", "recipe_8"]}` |

**Why:** IDs are precise. Name filters might miss or double-count.
```

### 3. Wire Understand's exclusion decisions to Act

When Understand demotes entities, this should surface to Act as:
> "Excluded refs: recipe_5, recipe_6. Remaining viable: recipe_3, recipe_4, recipe_8, recipe_9"

---

## Code Changes Needed

1. **prompts/act/crud.md** — Add exclusion patterns section
2. **prompts/act/read.md** — Add context reuse guidance
3. **src/alfred/prompts/injection.py** — Surface Understand's curation to Act

---

*Last updated: 2026-01-13*
