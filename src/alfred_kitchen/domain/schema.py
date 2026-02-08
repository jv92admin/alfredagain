"""
Kitchen Domain Schema Constants.

Phase 3a: Moved from tools/schema.py to domain/kitchen/.
These are kitchen-specific data constants that don't belong in core.
"""

from typing import Any


# =============================================================================
# Subdomain Scope
# =============================================================================

# Scope config for cross-domain awareness and implicit relationships
SUBDOMAIN_SCOPE: dict[str, dict[str, Any]] = {
    "recipes": {
        "implicit_children": ["recipe_ingredients"],  # Always inject together
        "description": "Recipes and their ingredients. Recipes link to recipe_ingredients.",
    },
    "inventory": {
        "normalization": "async",  # Background process normalizes ingredient_id
        "description": "User's pantry/fridge/freezer items.",
    },
    "shopping": {
        "normalization": "async",
        "influenced_by": ["recipes", "meal_plans", "inventory"],
        "description": "Shopping list. Often populated from recipes or meal plans.",
    },
    "preferences": {
        "description": "User preferences. Changes affect UX significantly.",
    },
    "meal_plans": {
        "implicit_dependencies": ["recipes"],  # Real meals need recipes
        "exception_meal_types": ["prep", "other"],  # These don't need recipes
        "related": ["tasks"],
        "description": "Meal planning calendar. Links to recipes and spawns tasks.",
    },
    "tasks": {
        "can_link_to": ["meal_plans", "recipes"],
        "linking_optional": True,
        "description": "Reminders and to-dos. Can be standalone or linked to meals/recipes.",
    },
    "history": {
        "description": "Cooking log. Simple event recording.",
    },
}


# =============================================================================
# Subdomain Registry
# =============================================================================

# Subdomain configuration type
SubdomainConfig = dict[str, list[str] | dict[str, str] | None]

# Maps high-level domains to database tables and complexity rules
# This is the ONLY place we maintain table groupings and auto-escalation rules
#
# complexity_rules:
#   - "mutation": complexity level for create/update/delete operations
#   - "read": complexity level for read operations (None = LLM decides)
#
SUBDOMAIN_REGISTRY: dict[str, SubdomainConfig] = {
    "inventory": {
        "tables": ["inventory", "ingredients"],
        # No complexity rules - simple single-table operations
    },
    "recipes": {
        "tables": ["recipes", "recipe_ingredients", "ingredients"],
        "complexity_rules": {"mutation": "high"},  # Linked tables require stronger model
    },
    "shopping": {
        "tables": ["shopping_list", "ingredients"],
        # No complexity rules - simple single-table operations
    },
    "meal_plans": {
        "tables": ["meal_plans", "recipes"],  # Meal plans reference recipes
        "complexity_rules": {"mutation": "medium"},  # References recipes, moderately complex
    },
    "tasks": {
        "tables": ["tasks"],
        # No complexity rules - simple single-table operations
        # Tasks can link to meal_plans, recipes, or be freeform
    },
    "preferences": {
        "tables": ["preferences", "flavor_preferences"],
        # No complexity rules - simple single-table operations
    },
    "history": {
        "tables": ["cooking_log"],
        # No complexity rules - event logging
    },
}


# =============================================================================
# Field Enums
# =============================================================================

# Enum values for categorical fields per subdomain
FIELD_ENUMS: dict[str, dict[str, list[str]]] = {
    "inventory": {
        "location": ["pantry", "fridge", "freezer", "counter", "cabinet"],
        "unit": ["piece", "lb", "lbs", "oz", "kg", "g", "gallon", "gallons", "carton", "cartons", "bottle", "can", "box", "bag", "bunch", "head", "cup", "tbsp", "tsp"],
    },
    "recipes": {
        "cuisine": ["italian", "mexican", "chinese", "indian", "american", "french", "japanese", "thai", "mediterranean", "korean"],
        "difficulty": ["easy", "medium", "hard"],
        "occasions": ["weeknight", "batch-prep", "hosting", "weekend", "comfort"],
        "health_tags": ["high-protein", "low-carb", "vegetarian", "vegan", "light", "gluten-free", "dairy-free", "keto"],
        "flavor_tags": ["spicy", "mild", "savory", "sweet", "tangy", "rich", "light", "umami", "other"],
        "equipment_tags": ["air-fryer", "instant-pot", "one-pot", "one-pan", "grill", "no-cook", "slow-cooker", "oven", "stovetop"],
    },
    "shopping": {
        "category": ["produce", "dairy", "meat", "seafood", "bakery", "frozen", "canned", "dry goods", "beverages", "snacks", "condiments", "spices"],
    },
    "meal_plans": {
        "meal_type": ["breakfast", "lunch", "dinner", "snack", "other"],
    },
    "tasks": {
        "category": ["prep", "shopping", "cleanup", "other"],
    },
    "preferences": {
        "cooking_skill_level": ["beginner", "intermediate", "advanced"],
        # planning_rhythm and current_vibes are freeform text[], no enum
    },
    "history": {
        "rating": ["1", "2", "3", "4", "5"],
    },
}


# =============================================================================
# Semantic Notes
# =============================================================================

# Semantic notes per subdomain (clarifications about common terms)
SEMANTIC_NOTES: dict[str, str] = {
    "inventory": """
**Note**: When user says "pantry" or "what's in my pantry", they typically mean ALL their food inventory, not just items with `location='pantry'`. Only filter by `location` if user explicitly asks about a specific storage location (e.g., "what's in my fridge?").
""",
    "recipes": """
**Semantic Search**: Use `_semantic` filter for intent-based queries:
- "light summer dinner" → `{"field": "_semantic", "op": "similar", "value": "light summer dinner"}`
- "quick comfort food" → `{"field": "_semantic", "op": "similar", "value": "quick comfort food"}`
- "something healthy" → `{"field": "_semantic", "op": "similar", "value": "healthy nutritious meal"}`
Combines with other filters (semantic narrows first, then other filters apply).

**recipe_ingredients.notes field:**
The `notes` field stores preparation instructions and qualifiers:
- "minced", "diced", "peeled" → prep instructions
- "fresh", "dried", "frozen" → state
- "medium", "large" → size
- "or substitute X" → alternatives
- "to taste" → optional amount

When reading recipes, surface notes to user (e.g., "garlic, minced" not just "garlic").
When creating recipes, put all qualifiers in notes, not in the name field.

**is_optional field:**
Set `is_optional: true` for garnishes, "to taste" ingredients, explicitly optional items.
""",
    "shopping": "",
    "meal_plans": """
**Note**: Meal plans store WHAT to eat WHEN. For reminders like "thaw chicken" or "buy wine", use `tasks` subdomain.

**meal_plans has:** date, meal_type, recipe_id, notes, servings
**meal_plans does NOT have:** recipe names, ingredients, instructions

**To get ingredients for planned meals:**
1. Read meal_plans (get recipe_ids)
2. Read recipes with those IDs (with ingredients)
""",
    "tasks": """
**Note**: Tasks are freeform to-dos. They can optionally link to a meal_plan or recipe, but don't have to.

**⚠️ When linking**: Use `meal_plan_id` (not `meal_plans_id`) in the task record, but if you need to query meal plans, the table is `meal_plans` (plural).
""",
    "preferences": "",
    "history": """
**Note**: Cooking log is an event log. Each entry represents one time a recipe was cooked.
Use this to answer "what did I cook last week?" or "how often do I make this?"
""",
}


# =============================================================================
# Subdomain Examples
# =============================================================================

# Subdomain-specific CRUD examples (just 1-2 key examples, not exhaustive)
SUBDOMAIN_EXAMPLES: dict[str, str] = {
    "inventory": """## Examples

Read all inventory: `{"tool": "db_read", "params": {"table": "inventory", "filters": [], "limit": 100}}`

Add single item: `{"tool": "db_create", "params": {"table": "inventory", "data": {"name": "milk", "quantity": 2, "unit": "gallons", "location": "fridge"}}}`

Add multiple items (batch): `{"tool": "db_create", "params": {"table": "inventory", "data": [{"name": "eggs", "quantity": 12, "unit": "count", "location": "fridge"}, {"name": "butter", "quantity": 1, "unit": "lb", "location": "fridge"}]}}`
""",
    "recipes": """## Examples

Read all recipes: `{"tool": "db_read", "params": {"table": "recipes", "filters": [], "limit": 20}}`

Search by keyword: `{"tool": "db_read", "params": {"table": "recipes", "filters": [{"field": "name", "op": "ilike", "value": "%chicken%"}], "limit": 20}}`

Search multiple keywords (OR): `{"tool": "db_read", "params": {"table": "recipes", "or_filters": [{"field": "name", "op": "ilike", "value": "%broccoli%"}, {"field": "name", "op": "ilike", "value": "%rice%"}], "limit": 10}}`

Create recipe: `{"tool": "db_create", "params": {"table": "recipes", "data": {"name": "Garlic Pasta", "cuisine": "italian", "difficulty": "easy", "servings": 2, "instructions": ["Boil pasta", "Sauté garlic", "Toss together"]}}}`

**⚠️ After creating recipe, create recipe_ingredients with the returned ID:**

Add ingredients: `{"tool": "db_create", "params": {"table": "recipe_ingredients", "data": [{"recipe_id": "<recipe-uuid>", "name": "pasta", "quantity": 8, "unit": "oz"}, {"recipe_id": "<recipe-uuid>", "name": "garlic", "quantity": 4, "unit": "cloves"}]}}`

Read ingredients: `{"tool": "db_read", "params": {"table": "recipe_ingredients", "filters": [{"field": "recipe_id", "op": "=", "value": "<recipe-uuid>"}]}}`
""",
    "shopping": """## Examples

Get shopping list: `{"tool": "db_read", "params": {"table": "shopping_list", "filters": [], "limit": 50}}`

Add multiple items (batch): `{"tool": "db_create", "params": {"table": "shopping_list", "data": [{"name": "eggs", "quantity": 12, "category": "dairy"}, {"name": "olive oil", "quantity": 1, "unit": "bottle"}]}}`

Mark item purchased: `{"tool": "db_update", "params": {"table": "shopping_list", "filters": [{"field": "id", "op": "=", "value": "<item-uuid>"}], "data": {"is_purchased": true}}}`

Delete all purchased items: `{"tool": "db_delete", "params": {"table": "shopping_list", "filters": [{"field": "is_purchased", "op": "=", "value": true}]}}`

Delete specific items by name: `{"tool": "db_delete", "params": {"table": "shopping_list", "filters": [{"field": "name", "op": "in", "value": ["milk", "eggs"]}]}}`
""",
    "meal_plans": """## Examples

Get meal plans: `{"tool": "db_read", "params": {"table": "meal_plans", "filters": [], "limit": 10}}`

Get this week's meals: `{"tool": "db_read", "params": {"table": "meal_plans", "filters": [{"field": "date", "op": ">=", "value": "2025-01-01"}, {"field": "date", "op": "<=", "value": "2025-01-07"}]}}`

Add to meal plan: `{"tool": "db_create", "params": {"table": "meal_plans", "data": {"recipe_id": "<recipe-uuid>", "date": "2025-01-02", "meal_type": "dinner", "servings": 2}}}`

Prep session (no recipe): `{"tool": "db_create", "params": {"table": "meal_plans", "data": {"date": "2025-01-05", "meal_type": "other", "notes": "Make chicken stock"}}}`

**Note**: Each row is a meal/cooking session on a date. For reminders/to-dos, use `tasks` subdomain.
""",
    "tasks": """## Examples

Get pending tasks: `{"tool": "db_read", "params": {"table": "tasks", "filters": [{"field": "completed", "op": "=", "value": false}]}}`

Create reminder: `{"tool": "db_create", "params": {"table": "tasks", "data": {"title": "Buy new chef's knife", "category": "shopping"}}}`

Create task with due date: `{"tool": "db_create", "params": {"table": "tasks", "data": {"title": "Thaw chicken", "due_date": "2025-01-06", "category": "prep"}}}`

Link task to meal plan: `{"tool": "db_create", "params": {"table": "tasks", "data": {"title": "Prep mise en place", "due_date": "2025-01-06", "category": "prep", "meal_plan_id": "<meal-plan-uuid>"}}}`

Mark complete: `{"tool": "db_update", "params": {"table": "tasks", "filters": [{"field": "id", "op": "=", "value": "<task-uuid>"}], "data": {"completed": true}}}`
""",
    "preferences": """## Examples

**Update current vibes:** `{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"current_vibes": ["chicken dishes", "curries", "grilling"]}}}`

**Update planning rhythm:** `{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"planning_rhythm": ["weekends only", "30min weeknights"]}}}`

**Update restrictions/allergies:** `{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"dietary_restrictions": ["vegetarian"], "allergies": ["peanuts"]}}}`

**Update equipment:** `{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"available_equipment": ["instant-pot", "air-fryer"]}}}`

**Read preferences:** `{"tool": "db_read", "params": {"table": "preferences", "filters": [], "limit": 1}}`
""",
    "history": """## Examples

Get recent cooking history: `{"tool": "db_read", "params": {"table": "cooking_log", "filters": [], "limit": 10}}`

Log a cooked meal: `{"tool": "db_create", "params": {"table": "cooking_log", "data": {"recipe_id": "<recipe-uuid>", "servings": 4, "rating": 5, "notes": "Came out great!"}}}`

Get history for recipe: `{"tool": "db_read", "params": {"table": "cooking_log", "filters": [{"field": "recipe_id", "op": "=", "value": "<recipe-uuid>"}]}}`

**Note:** Logging a meal auto-updates `flavor_preferences` via trigger.
""",
}


# =============================================================================
# Hardcoded Fallback Schemas (for development before migration)
# =============================================================================

FALLBACK_SCHEMAS: dict[str, str] = {
    "inventory": """## Available Tables (subdomain: inventory)

### inventory
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| ingredient_id | uuid | Yes |
| name | text | No |
| quantity | numeric | No |
| unit | text | No |
| location | text | Yes |
| notes | text | Yes |
| expiry_date | date | Yes |

### ingredients
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| name | text | No |
| aliases | text[] | Yes |
| category | text | Yes |
| default_unit | text | Yes |
""",
    "recipes": """## Available Tables (subdomain: recipes)

### recipes
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| name | text | No |
| description | text | Yes |
| cuisine | text | Yes |
| difficulty | text | Yes |
| prep_time_minutes | integer | Yes |
| cook_time_minutes | integer | Yes |
| servings | integer | Yes |
| instructions | text[] | No |
| tags | text[] | Yes |
| source_url | text | Yes |
| parent_recipe_id | uuid | Yes \u2190 FK to recipes.id for variations |

### recipe_ingredients (REQUIRED for each recipe!)
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| recipe_id | uuid | No \u2190 FK to recipes.id |
| user_id | uuid | No \u2190 auto-injected |
| ingredient_id | uuid | Yes |
| name | text | No |
| quantity | numeric | Yes |
| unit | text | Yes |
| notes | text | Yes |
| is_optional | boolean | No |

**\ud83d\udd17 Data Model: `recipes` + `recipe_ingredients`**

**Why separate tables:** Recipes store metadata + instructions. Ingredients are individual rows with their own IDs for precise updates.

| Operation | How |
|-----------|-----|
| CREATE recipe | `db_create` recipes \u2192 `db_create` recipe_ingredients with that recipe_id |
| DELETE recipe | `db_delete` recipes (ingredients CASCADE automatically) |
| UPDATE metadata | `db_update` on `recipes` table |
| UPDATE ingredient | `db_update` on `recipe_ingredients` by row ID |
| ADD ingredient | `db_create` on `recipe_ingredients` with recipe_id |
| REMOVE ingredient | `db_delete` on `recipe_ingredients` by row ID |

**Key:** Each ingredient has its own ID. Update by row ID, don't delete+recreate.

**Recipe Variations:**
- Use `parent_recipe_id` to link a variation to its base recipe
- Example: "Spicy Butter Chicken" with `parent_recipe_id` pointing to "Butter Chicken"

### ingredients
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| name | text | No |
| aliases | text[] | Yes |
| category | text | Yes |
""",
    "shopping": """## Available Tables (subdomain: shopping)

### shopping_list
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| ingredient_id | uuid | Yes |
| name | text | No |
| quantity | numeric | Yes |
| unit | text | Yes |
| category | text | Yes |
| is_purchased | boolean | No (default false) |
| source | text | Yes |
| notes | text | Yes |

### ingredients
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| name | text | No |
| category | text | Yes |
""",
    "meal_plans": """## Available Tables (subdomain: meal_plans)

### meal_plans
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| date | date | No |
| meal_type | text | No \u2190 breakfast, lunch, dinner, snack, or **other** (for experiments/stocks) |
| recipe_id | uuid | Yes \u2190 Link to recipe being cooked |
| notes | text | Yes |
| servings | integer | Yes (default 1) |

**Meal Types:**
- `breakfast`, `lunch`, `dinner`, `snack` = Standard meals
- `other` = Experiments, making stock, batch cooking base ingredients

**\ud83d\udd17 RELATED: `meal_plans` \u2192 `tasks`**

Tasks can link to meal_plans via `meal_plan_id`. On DELETE of a meal_plan:
- **Linked tasks are PRESERVED** (their meal_plan_id becomes NULL)
- You do NOT need to delete tasks before deleting the meal plan
- Just delete the meal_plan directly

### recipes
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| name | text | No |
| cuisine | text | Yes |
| difficulty | text | Yes |
""",
    "tasks": """## Available Tables (subdomain: tasks)

### tasks
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| title | text | No |
| due_date | date | Yes \u2190 Optional due date |
| category | text | Yes \u2190 prep, shopping, cleanup, other |
| completed | boolean | No (default false) |
| recipe_id | uuid | Yes \u2190 Optional: link to a recipe (SET NULL on delete) |
| meal_plan_id | uuid | Yes \u2190 Optional: link to a meal plan (SET NULL on delete) |

**Tasks are freeform by default.** They can optionally link to:
- A recipe (e.g., "Prep ingredients for butter chicken")
- A meal plan (e.g., "Thaw chicken for Monday's dinner")
- Or nothing (e.g., "Buy new chef's knife")

**\ud83d\udd17 FK Behavior:** If linked meal_plan or recipe is deleted, task survives with NULL reference.
You do NOT need to delete tasks before deleting their linked entities.

**Categories:**
- `prep` = Kitchen prep work (thaw, marinate, chop)
- `shopping` = Buying things
- `cleanup` = Kitchen maintenance
- `other` = Everything else
""",
    "preferences": """## Available Tables (subdomain: preferences)

### preferences
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| dietary_restrictions | text[] | Yes \u2190 HARD CONSTRAINTS: vegetarian, vegan, halal, kosher, etc. |
| allergies | text[] | Yes \u2190 HARD CONSTRAINTS: peanuts, shellfish, dairy, etc. |
| household_adults | integer | Yes (default 1) \u2190 Number of adults for portioning |
| household_kids | integer | Yes (default 0) \u2190 Number of kids (~0.5 portions each) |
| household_babies | integer | Yes (default 0) \u2190 Number of babies (0 portions) |
| cooking_skill_level | text | Yes \u2190 beginner, intermediate, advanced |
| available_equipment | text[] | Yes \u2190 instant-pot, air-fryer, grill, sous-vide, etc. |
| favorite_cuisines | text[] | Yes \u2190 italian, thai, mexican, comfort-food, etc. |
| disliked_ingredients | text[] | Yes |
| nutrition_goals | text[] | Yes \u2190 high-protein, low-carb, low-sodium, etc. |
| planning_rhythm | text[] | Yes \u2190 2-3 freeform schedule tags: "weekends only", "30min weeknights" |
| current_vibes | text[] | Yes \u2190 Up to 5 current interests: "more vegetables", "fusion experiments" |

**Field guidance:**
- `dietary_restrictions` and `allergies`: NEVER violated \u2014 hard constraints
- `planning_rhythm`: How they want to cook (schedule/time). Examples:
  - "just the weekend and reheat weekdays"
  - "mondays and wednesdays for 30 minutes"
  - "pretty flexible - no cooking tuesday"
- `current_vibes`: Current culinary interests/goals. Examples:
  - "experiment with fusion"
  - "trying to get more veg in"
  - "want to get good at salads"

### flavor_preferences
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| ingredient_id | uuid | No \u2190 FK to ingredients |
| preference_score | numeric | Yes \u2190 Positive = liked, Negative = disliked |
| times_used | integer | Yes \u2190 Auto-updated from cooking_log |
| last_used_at | timestamptz | Yes \u2190 Auto-updated from cooking_log |

**Note:** `flavor_preferences` is auto-updated by triggers when you log a cooked meal.
""",
    "history": """## Available Tables (subdomain: history)

### cooking_log
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| recipe_id | uuid | Yes \u2190 FK to recipes |
| cooked_at | timestamptz | Yes (default NOW()) |
| servings | integer | Yes |
| rating | integer | Yes \u2190 1-5 stars |
| notes | text | Yes |
| from_meal_plan_id | uuid | Yes \u2190 If cooked from meal plan |

**Cooking Log:**
- Log when you cook a recipe to track history
- Rate recipes 1-5 stars
- Links to flavor_preferences via trigger (auto-updates ingredient usage)
""",
}
