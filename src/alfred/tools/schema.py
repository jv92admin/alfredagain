"""
Alfred V3 - Schema Generation System.

Provides:
- SUBDOMAIN_REGISTRY: Maps subdomains to tables
- Auto-generation of table schemas from database
- Schema caching for performance

V3 Note: Personas and contextual examples have been moved to:
- alfred.prompts.personas (SUBDOMAIN_PERSONAS, get_persona_for_subdomain, etc.)
- alfred.prompts.examples (get_contextual_examples)

Backwards-compatible re-exports are provided for existing code.
"""

import time
from typing import Any

from alfred.db.client import get_client

# =============================================================================
# V3 Re-exports (moved to alfred.prompts, kept here for backwards compat)
# =============================================================================
# New code should import from alfred.prompts directly

# These will be defined later in this file for now (duplicated)
# In a future cleanup, remove the local definitions and uncomment these:
# from alfred.prompts.personas import (
#     SUBDOMAIN_PERSONAS,
#     SUBDOMAIN_SCOPE,
#     get_persona_for_subdomain,
#     get_scope_for_subdomain,
#     get_subdomain_dependencies_summary,
# )
# from alfred.prompts.examples import get_contextual_examples


# =============================================================================
# NOTE: Personas have moved to alfred.prompts.personas
# =============================================================================
# SUBDOMAIN_PERSONAS was here but is now in personas.py
# The get_persona_for_subdomain function below is kept for backwards compat
# but forwards to the canonical source.


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
        "tables": ["meal_plans"],  # Just meal_plans - recipes fetched via separate step if needed
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


def get_subdomain_tables(subdomain: str) -> list[str]:
    """Get the list of tables for a subdomain."""
    config = SUBDOMAIN_REGISTRY.get(subdomain, {})
    if isinstance(config, dict):
        return config.get("tables", [])
    # Backwards compatibility if somehow still a list
    return config if isinstance(config, list) else []


def get_complexity_rules(subdomain: str) -> dict[str, str] | None:
    """Get complexity rules for a subdomain."""
    config = SUBDOMAIN_REGISTRY.get(subdomain, {})
    if isinstance(config, dict):
        return config.get("complexity_rules")
    return None


def get_persona_for_subdomain(subdomain: str, step_type: str = "crud") -> str:
    """Get the persona text for a subdomain.
    
    DEPRECATED: Import from alfred.prompts.personas instead.
    This function forwards to the canonical source for backwards compat.
    
    Args:
        subdomain: The subdomain (recipes, inventory, shopping, etc.)
        step_type: The step type (read, write, generate, analyze).
    """
    # Forward to canonical source
    from alfred.prompts.personas import get_persona_for_subdomain as _get_persona
    return _get_persona(subdomain, step_type)


def get_scope_for_subdomain(subdomain: str) -> str:
    """Get a formatted scope description for a subdomain."""
    scope = SUBDOMAIN_SCOPE.get(subdomain, {})
    if not scope:
        return ""
    
    lines = []
    
    # Description
    if "description" in scope:
        lines.append(f"**Scope:** {scope['description']}")
    
    # Influenced by
    if "influenced_by" in scope:
        influenced = ", ".join(scope["influenced_by"])
        lines.append(f"**Influenced by:** {influenced}")
    
    # Implicit children
    if "implicit_children" in scope:
        children = ", ".join(scope["implicit_children"])
        lines.append(f"**Linked tables:** Always handle {children} together with this subdomain.")
    
    # Implicit dependencies
    if "implicit_dependencies" in scope:
        deps = ", ".join(scope["implicit_dependencies"])
        exceptions = scope.get("exception_meal_types", [])
        if exceptions:
            exc_str = ", ".join(exceptions)
            lines.append(f"**Dependencies:** Usually needs {deps} (except for {exc_str} meal types).")
        else:
            lines.append(f"**Dependencies:** Usually needs {deps}.")
    
    # Related
    if "related" in scope:
        related = ", ".join(scope["related"])
        lines.append(f"**Works with:** {related}")
    
    return "\n".join(lines)


def get_subdomain_dependencies_summary() -> str:
    """
    Get a compact summary of subdomain dependencies for Think node.
    
    This helps Think understand relationships between domains when planning.
    
    Returns:
        Markdown-formatted summary of key domain relationships
    """
    lines = [
        "## DOMAIN KNOWLEDGE",
        "",
        "Key relationships between data domains:",
        "",
        "- **Meal plans → Recipes**: Real meals (breakfast/lunch/dinner/snack) should have recipes. Exception: `prep` and `other` meal types don't require recipes.",
        "- **Recipes → Recipe Ingredients**: Always created together as one unit. Recipe saves include ingredients.",
        "- **Shopping ← Multiple sources**: Shopping lists are influenced by recipes, meal plans, and inventory. Check what exists before adding.",
        "- **Tasks ← Meal plans**: Tasks often flow from meal plans (prep reminders, shopping tasks). Prefer linking to meal_plan_id.",
        "- **Inventory ↔ Shopping**: Items in inventory shouldn't need to be on shopping list. Cross-check when adding.",
        "",
        "**About Cooking Schedule:** The user's cooking schedule describes WHEN THEY COOK (batch cook, prep), not when they eat. 'weekends only' = they cook on weekends (maybe batch for the week). 'dinner wednesdays' = they cook dinner on Wednesdays.",
    ]
    return "\n".join(lines)


# =============================================================================
# Schema Fetching
# =============================================================================


async def get_table_schema(table: str) -> dict[str, Any]:
    """
    Fetch column info for a table from Postgres information_schema.

    Uses an RPC function that must be created in the database:
    See migrations/004_schema_introspection.sql

    Args:
        table: Table name

    Returns:
        Dict with table name and column info
    """
    client = get_client()

    try:
        result = client.rpc("get_table_columns", {"table_name": table}).execute()

        return {
            "table": table,
            "columns": [
                {
                    "name": col["column_name"],
                    "type": col["data_type"],
                    "nullable": col["is_nullable"] == "YES",
                }
                for col in result.data
            ],
        }
    except Exception as e:
        # Fallback: return empty schema if RPC not available
        # This allows development before migration is run
        return {
            "table": table,
            "columns": [],
            "error": str(e),
        }


async def get_subdomain_schema(subdomain: str) -> str:
    """
    Generate markdown schema for all tables in a subdomain.

    Args:
        subdomain: Subdomain name (e.g., "recipes", "inventory")

    Returns:
        Markdown-formatted schema for LLM consumption
    """
    tables = get_subdomain_tables(subdomain)

    if not tables:
        return f"Unknown subdomain: {subdomain}"

    schemas = []
    for table in tables:
        schema = await get_table_schema(table)
        schemas.append(schema)

    return format_as_markdown(schemas, subdomain)


# System columns to hide from LLM (auto-injected by CRUD tools)
HIDDEN_COLUMNS = {"user_id", "created_at", "updated_at"}


def format_as_markdown(schemas: list[dict], subdomain: str) -> str:
    """
    Convert schema dicts to readable markdown for LLM.

    Filters out system columns (user_id, created_at, updated_at) that
    are auto-injected by CRUD tools.

    Args:
        schemas: List of table schemas
        subdomain: Subdomain name for header

    Returns:
        Markdown string
    """
    lines = [f"## Available Tables (subdomain: {subdomain})", ""]

    for schema in schemas:
        table = schema["table"]
        columns = schema.get("columns", [])

        lines.append(f"### {table}")

        if not columns:
            if "error" in schema:
                lines.append(f"*Schema unavailable: {schema['error']}*")
            else:
                lines.append("*No columns found*")
            lines.append("")
            continue

        # Filter out hidden system columns
        visible_columns = [
            col for col in columns if col["name"] not in HIDDEN_COLUMNS
        ]

        lines.append("| Column | Type | Nullable |")
        lines.append("|--------|------|----------|")

        for col in visible_columns:
            nullable = "Yes" if col.get("nullable", True) else "No"
            lines.append(f"| {col['name']} | {col['type']} | {nullable} |")

        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Schema Cache
# =============================================================================


class SchemaCache:
    """
    Cache schemas per session to avoid repeated DB calls.

    Schemas rarely change, so we cache with a TTL.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[str, float]] = {}
        self._ttl = ttl_seconds

    async def get(self, subdomain: str) -> str:
        """
        Get schema for subdomain, using cache if valid.

        Args:
            subdomain: Subdomain name

        Returns:
            Markdown schema string
        """
        now = time.time()

        if subdomain in self._cache:
            schema, timestamp = self._cache[subdomain]
            if now - timestamp < self._ttl:
                return schema

        # Fetch fresh schema
        schema = await get_subdomain_schema(subdomain)
        self._cache[subdomain] = (schema, now)
        return schema

    def clear(self) -> None:
        """Clear the cache."""
        self._cache = {}

    def invalidate(self, subdomain: str) -> None:
        """Invalidate cache for a specific subdomain."""
        self._cache.pop(subdomain, None)


# Global cache instance
schema_cache = SchemaCache()


# =============================================================================
# Filter Schema + Field Enums
# =============================================================================

# Filter operators documentation
FILTER_SCHEMA = """## Filter Syntax

Structure: `{"field": "<column>", "op": "<operator>", "value": <value>}`

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Exact match | `{"field": "id", "op": "=", "value": "uuid"}` |
| `>` `<` `>=` `<=` | Comparison | `{"field": "quantity", "op": ">", "value": 5}` |
| `in` | Value in array | `{"field": "name", "op": "in", "value": ["milk", "eggs"]}` |
| `ilike` | Pattern match (% = wildcard) | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Null check | `{"field": "expiry_date", "op": "is_null", "value": true}` |
| `similar` | **Semantic search** (recipes only) | `{"field": "_semantic", "op": "similar", "value": "light summer dinner"}` |

### Semantic Search (`_semantic` filter)

For intent-based recipe queries, use the `_semantic` filter:
- **Good for**: "light summer dinner", "quick comfort food", "healthy breakfast", "something like pasta carbonara"
- **Combines with**: Other filters are applied AFTER semantic narrowing
- **Example**: Find light recipes with chicken:
  ```json
  {"filters": [
    {"field": "_semantic", "op": "similar", "value": "light healthy meal"},
    {"field": "name", "op": "ilike", "value": "%chicken%"}
  ]}
  ```

"""

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


def get_subdomain_context(subdomain: str) -> str:
    """
    Get complete subdomain context for Act node:
    1. Filter schema (operators)
    2. Field enums (allowed values for categorical fields)
    3. Semantic notes (clarifications like "pantry = all inventory")
    4. CRUD examples
    """
    parts = [FILTER_SCHEMA]
    
    # Add field enums if available
    enums = FIELD_ENUMS.get(subdomain, {})
    if enums:
        parts.append("## Field Values (Enums)\n")
        for field, values in enums.items():
            parts.append(f"- `{field}`: {', '.join(values)}")
        parts.append("")
    
    # Add semantic notes if available
    notes = SEMANTIC_NOTES.get(subdomain, "")
    if notes.strip():
        parts.append(notes)
    
    # Add examples
    examples = SUBDOMAIN_EXAMPLES.get(subdomain, "")
    if examples:
        parts.append(examples)
    
    return "\n".join(parts)


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
| parent_recipe_id | uuid | Yes ← FK to recipes.id for variations |

### recipe_ingredients (REQUIRED for each recipe!)
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| recipe_id | uuid | No ← FK to recipes.id |
| user_id | uuid | No ← auto-injected |
| ingredient_id | uuid | Yes |
| name | text | No |
| quantity | numeric | Yes |
| unit | text | Yes |
| notes | text | Yes |
| is_optional | boolean | No |

**🔗 Data Model: `recipes` + `recipe_ingredients`**

**Why separate tables:** Recipes store metadata + instructions. Ingredients are individual rows with their own IDs for precise updates.

| Operation | How |
|-----------|-----|
| CREATE recipe | `db_create` recipes → `db_create` recipe_ingredients with that recipe_id |
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
| meal_type | text | No ← breakfast, lunch, dinner, snack, or **other** (for experiments/stocks) |
| recipe_id | uuid | Yes ← Link to recipe being cooked |
| notes | text | Yes |
| servings | integer | Yes (default 1) |

**Meal Types:**
- `breakfast`, `lunch`, `dinner`, `snack` = Standard meals
- `other` = Experiments, making stock, batch cooking base ingredients

**🔗 RELATED: `meal_plans` → `tasks`**

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
| due_date | date | Yes ← Optional due date |
| category | text | Yes ← prep, shopping, cleanup, other |
| completed | boolean | No (default false) |
| recipe_id | uuid | Yes ← Optional: link to a recipe (SET NULL on delete) |
| meal_plan_id | uuid | Yes ← Optional: link to a meal plan (SET NULL on delete) |

**Tasks are freeform by default.** They can optionally link to:
- A recipe (e.g., "Prep ingredients for butter chicken")
- A meal plan (e.g., "Thaw chicken for Monday's dinner")
- Or nothing (e.g., "Buy new chef's knife")

**🔗 FK Behavior:** If linked meal_plan or recipe is deleted, task survives with NULL reference.
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
| dietary_restrictions | text[] | Yes ← HARD CONSTRAINTS: vegetarian, vegan, halal, kosher, etc. |
| allergies | text[] | Yes ← HARD CONSTRAINTS: peanuts, shellfish, dairy, etc. |
| household_adults | integer | Yes (default 1) ← Number of adults for portioning |
| household_kids | integer | Yes (default 0) ← Number of kids (~0.5 portions each) |
| household_babies | integer | Yes (default 0) ← Number of babies (0 portions) |
| cooking_skill_level | text | Yes ← beginner, intermediate, advanced |
| available_equipment | text[] | Yes ← instant-pot, air-fryer, grill, sous-vide, etc. |
| favorite_cuisines | text[] | Yes ← italian, thai, mexican, comfort-food, etc. |
| disliked_ingredients | text[] | Yes |
| nutrition_goals | text[] | Yes ← high-protein, low-carb, low-sodium, etc. |
| planning_rhythm | text[] | Yes ← 2-3 freeform schedule tags: "weekends only", "30min weeknights" |
| current_vibes | text[] | Yes ← Up to 5 current interests: "more vegetables", "fusion experiments" |

**Field guidance:**
- `dietary_restrictions` and `allergies`: NEVER violated — hard constraints
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
| ingredient_id | uuid | No ← FK to ingredients |
| preference_score | numeric | Yes ← Positive = liked, Negative = disliked |
| times_used | integer | Yes ← Auto-updated from cooking_log |
| last_used_at | timestamptz | Yes ← Auto-updated from cooking_log |

**Note:** `flavor_preferences` is auto-updated by triggers when you log a cooked meal.
""",
    "history": """## Available Tables (subdomain: history)

### cooking_log
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| recipe_id | uuid | Yes ← FK to recipes |
| cooked_at | timestamptz | Yes (default NOW()) |
| servings | integer | Yes |
| rating | integer | Yes ← 1-5 stars |
| notes | text | Yes |
| from_meal_plan_id | uuid | Yes ← If cooked from meal plan |

**Cooking Log:**
- Log when you cook a recipe to track history
- Rate recipes 1-5 stars
- Links to flavor_preferences via trigger (auto-updates ingredient usage)
""",
}


async def get_schema_with_fallback(subdomain: str) -> str:
    """
    Get schema for subdomain, falling back to hardcoded if DB unavailable.
    
    Includes:
    - Table column definitions (schema)
    - Subdomain-specific CRUD examples with exact filter syntax

    Args:
        subdomain: Subdomain name

    Returns:
        Markdown schema string + CRUD examples
    """
    try:
        schema = await schema_cache.get(subdomain)
        # If schema is empty or has errors, use fallback
        if "No columns found" in schema or "Schema unavailable" in schema:
            schema = FALLBACK_SCHEMAS.get(subdomain, schema)
    except Exception:
        schema = FALLBACK_SCHEMAS.get(
            subdomain, f"Unknown subdomain: {subdomain}"
        )
    
    # Append subdomain context (filter schema + enums + notes + examples)
    context = get_subdomain_context(subdomain)
    if context:
        return f"{schema}\n{context}"
    return schema


# =============================================================================
# Schema Drift Validation
# =============================================================================


async def validate_schema_drift() -> list[str]:
    """
    Compare FALLBACK_SCHEMAS to actual DB schema and report drift.
    
    Call this on startup to catch schema mismatches early.
    
    Returns:
        List of warning messages (empty if no drift)
    """
    warnings = []
    
    for subdomain in SUBDOMAIN_REGISTRY:
        tables = get_subdomain_tables(subdomain)
        for table in tables:
            try:
                db_schema = await get_table_schema(table)
                db_columns = {col["name"] for col in db_schema.get("columns", [])}
                
                if not db_columns:
                    warnings.append(f"⚠️ Table '{table}' not found in database")
                    continue
                
                # Parse fallback schema for this subdomain
                fallback = FALLBACK_SCHEMAS.get(subdomain, "")
                if f"### {table}" in fallback:
                    # Extract column names from markdown table
                    import re
                    pattern = rf"### {table}\n.*?\n\|.*?\n\|.*?\n((?:\|.*?\n)+)"
                    match = re.search(pattern, fallback, re.DOTALL)
                    if match:
                        lines = match.group(1).strip().split("\n")
                        fallback_columns = set()
                        for line in lines:
                            parts = line.split("|")
                            if len(parts) >= 2:
                                col_name = parts[1].strip()
                                if col_name and col_name not in ("Column", "---"):
                                    fallback_columns.add(col_name)
                        
                        # Compare (ignore hidden columns)
                        fallback_visible = fallback_columns - HIDDEN_COLUMNS
                        db_visible = db_columns - HIDDEN_COLUMNS
                        
                        missing_in_db = fallback_visible - db_visible
                        missing_in_fallback = db_visible - fallback_visible
                        
                        if missing_in_db:
                            warnings.append(
                                f"⚠️ {subdomain}.{table}: Columns in fallback but not DB: {missing_in_db}"
                            )
                        if missing_in_fallback:
                            warnings.append(
                                f"ℹ️ {subdomain}.{table}: Columns in DB but not fallback: {missing_in_fallback}"
                            )
            except Exception as e:
                warnings.append(f"❌ Error checking {subdomain}.{table}: {e}")
    
    return warnings


async def log_schema_drift_warnings():
    """Log schema drift warnings on startup."""
    import logging
    logger = logging.getLogger(__name__)
    
    warnings = await validate_schema_drift()
    if warnings:
        logger.warning("Schema drift detected:")
        for w in warnings:
            logger.warning(f"  {w}")
    else:
        logger.info("Schema validation passed - no drift detected")

