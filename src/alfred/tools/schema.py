"""
Alfred V2 - Schema Generation System.

Provides:
- SUBDOMAIN_REGISTRY: Maps subdomains to tables
- Auto-generation of table schemas from database
- Schema caching for performance
"""

import time
from typing import Any

from alfred.db.client import get_client


# =============================================================================
# Subdomain Registry
# =============================================================================

# Maps high-level domains to database tables
# This is the ONLY place we maintain table groupings
SUBDOMAIN_REGISTRY: dict[str, list[str]] = {
    "inventory": ["inventory", "ingredients"],
    "recipes": ["recipes", "recipe_ingredients", "ingredients"],
    "shopping": ["shopping_list", "ingredients"],  # shopping_list IS the items (no separate items table)
    "meal_plan": ["meal_plans", "recipes"],  # meal_plans has recipe_id directly
    "preferences": ["preferences"],  # Table is named 'preferences', not 'user_preferences'
}


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
    tables = SUBDOMAIN_REGISTRY.get(subdomain, [])

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
    },
    "shopping": {
        "category": ["produce", "dairy", "meat", "seafood", "bakery", "frozen", "canned", "dry goods", "beverages", "snacks", "condiments", "spices"],
    },
    "meal_plan": {
        "meal_type": ["breakfast", "lunch", "dinner", "snack"],
    },
    "preferences": {
        "cooking_skill_level": ["beginner", "intermediate", "advanced"],
    },
}

# Semantic notes per subdomain (clarifications about common terms)
SEMANTIC_NOTES: dict[str, str] = {
    "inventory": """
**Note**: When user says "pantry" or "what's in my pantry", they typically mean ALL their food inventory, not just items with `location='pantry'`. Only filter by `location` if user explicitly asks about a specific storage location (e.g., "what's in my fridge?").
""",
    "recipes": "",
    "shopping": "",
    "meal_plan": "",
    "preferences": "",
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

**Search recipes by keywords** (use `or_filters` for fuzzy matching):
```json
{"tool": "db_read", "params": {
  "table": "recipes",
  "or_filters": [
    {"field": "name", "op": "ilike", "value": "%broccoli%"},
    {"field": "name", "op": "ilike", "value": "%cheese%"},
    {"field": "name", "op": "ilike", "value": "%rice%"}
  ],
  "limit": 10
}}
```
This finds recipes matching ANY of the keywords (OR logic).

Create recipe: `{"tool": "db_create", "params": {"table": "recipes", "data": {"name": "Garlic Pasta", "cuisine": "italian", "difficulty": "easy", "servings": 2, "instructions": ["Boil pasta", "Sauté garlic", "Toss together"]}}}`

**⚠️ After creating recipe, you MUST create recipe_ingredients!**
Get the recipe `id` from the response, then:
```json
{"tool": "db_create", "params": {"table": "recipe_ingredients", "data": [
  {"recipe_id": "<recipe-uuid>", "name": "pasta", "quantity": 8, "unit": "oz"},
  {"recipe_id": "<recipe-uuid>", "name": "garlic", "quantity": 4, "unit": "cloves"},
  {"recipe_id": "<recipe-uuid>", "name": "olive oil", "quantity": 2, "unit": "tbsp"}
]}}
```

Read recipe ingredients: `{"tool": "db_read", "params": {"table": "recipe_ingredients", "filters": [{"field": "recipe_id", "op": "=", "value": "<recipe-uuid>"}]}}`
""",
    "shopping": """## Examples

Get shopping list: `{"tool": "db_read", "params": {"table": "shopping_list", "filters": [], "limit": 50}}`

Add multiple items (batch): `{"tool": "db_create", "params": {"table": "shopping_list", "data": [{"name": "eggs", "quantity": 12, "category": "dairy"}, {"name": "olive oil", "quantity": 1, "unit": "bottle"}]}}`

Mark item purchased: `{"tool": "db_update", "params": {"table": "shopping_list", "filters": [{"field": "id", "op": "=", "value": "<item-uuid>"}], "data": {"is_purchased": true}}}`

Delete all purchased items: `{"tool": "db_delete", "params": {"table": "shopping_list", "filters": [{"field": "is_purchased", "op": "=", "value": true}]}}`

Delete specific items by name: `{"tool": "db_delete", "params": {"table": "shopping_list", "filters": [{"field": "name", "op": "in", "value": ["milk", "eggs"]}]}}`
""",
    "meal_plan": """## Examples

Get meal plans: `{"tool": "db_read", "params": {"table": "meal_plans", "filters": [], "limit": 10}}`

Add to meal plan: `{"tool": "db_create", "params": {"table": "meal_plans", "data": {"recipe_id": "<recipe-uuid>", "date": "2025-01-02", "meal_type": "dinner", "servings": 2}}}`

**Note**: `meal_plans` stores items directly (each row is a meal on a date). Not a parent-child structure.
""",
    "preferences": """## Examples

Get preferences: `{"tool": "db_read", "params": {"table": "preferences", "filters": [], "limit": 1}}`

Update preferences: `{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"favorite_cuisines": ["italian", "mexican"]}}}`
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

### recipe_ingredients (REQUIRED for each recipe!)
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| recipe_id | uuid | No ← FK to recipes.id |
| ingredient_id | uuid | Yes |
| name | text | No |
| quantity | numeric | Yes |
| unit | text | Yes |
| notes | text | Yes |
| is_optional | boolean | No |

**⚠️ IMPORTANT: recipes + recipe_ingredients are linked!**
- When CREATING a recipe: First create `recipes` row, get its `id`, then create `recipe_ingredients` rows with that `recipe_id`
- When READING ingredients: Query `recipe_ingredients` WHERE `recipe_id` = the recipe's id
- A recipe without `recipe_ingredients` rows is incomplete!

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
    "meal_plan": """## Available Tables (subdomain: meal_plan)

### meal_plans
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| date | date | No |
| meal_type | text | No |
| recipe_id | uuid | Yes |
| notes | text | Yes |
| servings | integer | Yes (default 1) |

### recipes
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| name | text | No |
| cuisine | text | Yes |
| difficulty | text | Yes |
""",
    "preferences": """## Available Tables (subdomain: preferences)

### preferences
| Column | Type | Nullable |
|--------|------|----------|
| id | uuid | No |
| dietary_restrictions | text[] | Yes |
| allergies | text[] | Yes |
| favorite_cuisines | text[] | Yes |
| disliked_ingredients | text[] | Yes |
| cooking_skill_level | text | Yes (default 'intermediate') |
| household_size | integer | Yes (default 1) |
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
    
    for subdomain, tables in SUBDOMAIN_REGISTRY.items():
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

