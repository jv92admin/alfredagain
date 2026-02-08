"""
Kitchen-specific Act prompt injections.

Provides domain-specific examples and guidance that get appended
to the core Act prompts for each step type.
"""

READ_INJECTION = """\
## Kitchen-Specific Read Patterns

### Broader Intent Before Filtering

When reading inventory, **default to ALL items** unless user explicitly requests a specific location.

| User says | Intent | Filter |
|-----------|--------|--------|
| "What do I have?" | All inventory | `filters: []` |
| "What's in my pantry?" | All inventory | `filters: []` |
| "Show my kitchen" | All inventory | `filters: []` |
| "What's in my fridge?" | Specific location | `location = 'fridge'` |
| "What's in my freezer?" | Specific location | `location = 'freezer'` |

**"Pantry" and "kitchen" are colloquial terms for all food inventory.**

### Think Intent Examples

| Think said | You do |
|-----------|--------|
| "Read saved recipes" | Read ALL recipes (`filters: []`) |
| "Read recipes matching 'chicken'" | Filter by `name ilike %chicken%` |
| "Read user's inventory" | Read ALL inventory items |

### Semantic Search (Recipes only)

Find recipes by intent, not keywords:
```json
{
  "table": "recipes",
  "filters": [
    {"field": "_semantic", "op": "similar", "value": "quick weeknight dinner"}
  ]
}
```
**Note:** Only works for `recipes` table. Uses embeddings for conceptual matching.

### Kitchen-Specific Notes

- `tags` field on recipes is NOT reliably queryable — use semantic search or read all and analyze instead.
- For recipes: only fetch `instructions` field if step explicitly needs it (e.g., "with instructions", "full recipe"). Otherwise save tokens.
- Use `occasions` field with `contains` operator: `{"field": "occasions", "op": "contains", "value": ["weeknight"]}`
"""

WRITE_INJECTION = """\
## Kitchen-Specific Write Patterns

### Cascade Behavior

- `recipes` → `recipe_ingredients`: **CASCADE** (just delete recipes, ingredients auto-delete)
- Other tables: delete children first, then parent

### Batch Insert Example (Recipe Ingredients)

```json
{
  "tool": "db_create",
  "params": {
    "table": "recipe_ingredients",
    "data": [
      {"recipe_id": "gen_recipe_1", "name": "garlic", "quantity": 2, "unit": "cloves"},
      {"recipe_id": "gen_recipe_1", "name": "olive oil", "quantity": 2, "unit": "tbsp"},
      {"recipe_id": "gen_recipe_2", "name": "chicken", "quantity": 1, "unit": "lb"}
    ]
  }
}
```
"""

ANALYZE_INJECTION = """\
## Kitchen-Specific Analysis Patterns

### Common Kitchen Analyses

- **Inventory vs Shopping List:** Items on shopping list already in inventory
- **Recipe vs Inventory:** Ingredients needed that aren't in stock
- **Meal Plan Gaps:** Days/meals not yet planned
- **Expiring Items:** Inventory items nearing expiry that should be used

### Ask User Example

```json
{
  "action": "ask_user",
  "question": "I see 6 recipes that work with your inventory. Should I prioritize using the chicken (expires Jan 15) or the cod (expires Jan 17)?",
  "data": {
    "partial_analysis": {
      "viable_recipes": 6,
      "expiring_proteins": ["chicken (Jan 15)", "cod (Jan 17)"],
      "decision_needed": "protein_priority"
    }
  }
}
```
"""

GENERATE_INJECTION = """\
## Kitchen-Specific Generation Quality

### Recipe Generation

- Don't generate generic "Chicken with Rice" — create something worth cooking
- Every recipe should have a "wow factor" (technique, flavor combo, texture contrast)
- Every meal plan should show thoughtful balance (variety, logistics, leftovers)
- Recipes must be cookable (real ingredients, real times, real techniques)
- Meal plans must be achievable (realistic prep, leftovers planned, not too ambitious)

### Personalization

- **Dietary restrictions** → HARD constraints, never violate
- **Cuisines** → Favor their preferences but suggest variety
- **Equipment** → Design for what they have (no sous vide if they lack the gear)
- **Current vibes** → What they're in the mood for

### Entity Tagging

Generated content refs use kitchen entity types:
- First recipe → `gen_recipe_1`
- First meal plan → `gen_meal_plan_1`
- etc.
"""

# Map step type to injection content
ACT_INJECTIONS: dict[str, str] = {
    "read": READ_INJECTION,
    "write": WRITE_INJECTION,
    "analyze": ANALYZE_INJECTION,
    "generate": GENERATE_INJECTION,
}
