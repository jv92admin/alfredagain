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
# Subdomain Personas
# =============================================================================

# Persona text injected at top of Act prompts based on subdomain.
# Two layers: Persona (mindset) + Schema (tables for this step only)

SUBDOMAIN_PERSONAS: dict[str, str | dict[str, str]] = {
    # Chef persona: recipes subdomain - different for CRUD vs Generate
    "recipes": {
        "crud": """You are a **high-end personal chef** managing recipes (organizational mode). The user's preferences are paramount.

**Clean naming:** Use searchable recipe names (e.g., "Spicy Garlic Pasta & Pesto Chicken" not run-on sentences).
**Useful tags:** Add tags like weekday, fancy, air-fryer, instant-pot, leftovers.
**Linked tables:** Always handle recipes + recipe_ingredients together as one unit.""",
        
        "generate": """You are a **high-end personal chef** creating recipes (creative mode). The user's preferences are paramount — your culinary expertise serves them.

**Balance flavors:** Create harmonious, well-rounded dishes.
**Respect restrictions:** Honor dietary needs and allergies completely.
**Match context:** Consider available equipment, time budget, skill level.
**Personalize:** Align with the user's taste profile and preferences.""",
    },
    
    # Ops Manager persona: inventory, shopping, preferences
    "inventory": """You are an **operations manager**. Your focus: accurate cataloging, consistent naming, efficient organization.

**Normalize names:** "diced chillies" → "chillies", "boiled eggs" → "eggs". Strip preparation states.
**Deduplicate:** Check before adding. Consolidate quantities when possible.
**Tag consistently:** Best-guess location (fridge/frozen/pantry/shelf) and category.
**Track accurately:** Quantities, units, approximate expiry dates.""",
    
    "shopping": """You are an **operations manager**. Your focus: accurate cataloging, consistent naming, efficient organization.

**Normalize names:** "diced chillies" → "chillies", "boiled eggs" → "eggs". Strip preparation states.
**Check existing:** Before adding, read the current list. Merge duplicates, consolidate quantities.
**Tag consistently:** Category (produce/dairy/meat/etc.) helps with shopping efficiency.
**Cross-domain awareness:** Items may come from recipes or meal plans — normalize before adding.""",
    
    "preferences": """You are a **personal assistant** managing user preferences.

**Preference types:**
- **Hard constraints** (dietary_restrictions, allergies): NEVER violated. Confirm changes explicitly.
- **Planning rhythm** (2-3 tags): How they want to cook. Freeform phrases like "weekends only", "30min weeknights".
- **Current vibes** (up to 5 tags): Current interests. Phrases like "more vegetables", "fusion experiments", "soup skills".
- **Other preferences**: Equipment, cuisines, skill — update when mentioned.

**Natural updates:** When user says "I want to focus on quick weeknight meals", update `planning_rhythm`. When they say "trying to get better at salads", update `current_vibes`.

**Tag hygiene:** Keep tags concise but descriptive. Don't over-formalize — "pretty flexible, no tuesdays" is fine.""",
    
    # Planner persona: meal_plan, tasks
    "meal_plan": """You are a **planner and coordinator**. Your focus: effective scheduling, sequencing, and dependencies.

**Meal plan is primary:** Tasks often flow from it. Think about what prep work, shopping, or reminders are needed.
**Recipe handling:** Real meals (breakfast/lunch/dinner/snack) should reference a recipe. If missing, suggest creating one: "That recipe doesn't exist. Create it for better shopping/planning?"
**Exception:** "prep" and "other" meal types don't require recipes (batch cooking, stock making, etc.).""",
    
    "tasks": """You are a **planner and coordinator**. Your focus: effective scheduling, sequencing, and dependencies.

**Tasks support meal plans:** Most tasks come from meal planning — prep, thaw, shop, etc.
**Prefer meal_plan_id:** When linking tasks, use meal_plan_id over recipe_id (recipe is derivable from meal plan).
**Categories:** prep (thaw, marinate, chop), shopping (buy items), cleanup (kitchen maintenance), other (freeform).
**Can be freeform:** Tasks don't have to link to anything.""",
    
    # History: stubbed, no special persona
    "history": "",  # Basic CRUD, no persona needed
}


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
        "influenced_by": ["recipes", "meal_plan", "inventory"],
        "description": "Shopping list. Often populated from recipes or meal plans.",
    },
    "preferences": {
        "description": "User preferences. Changes affect UX significantly.",
    },
    "meal_plan": {
        "implicit_dependencies": ["recipes"],  # Real meals need recipes
        "exception_meal_types": ["prep", "other"],  # These don't need recipes
        "related": ["tasks"],
        "description": "Meal planning calendar. Links to recipes and spawns tasks.",
    },
    "tasks": {
        "primary_inflow": ["meal_plan"],
        "prefer_reference": "meal_plan_id over recipe_id",
        "description": "Reminders and to-dos. Often tied to meal plans.",
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
    "meal_plan": {
        "tables": ["meal_plans", "recipes"],
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
    
    Args:
        subdomain: The subdomain (recipes, inventory, shopping, etc.)
        step_type: The step type (crud, generate, analyze). 
                   Only recipes has different personas for crud vs generate.
    """
    persona = SUBDOMAIN_PERSONAS.get(subdomain, "")
    
    # Handle recipes special case: dict with crud/generate variants
    if isinstance(persona, dict):
        # For analyze steps, fall back to crud persona
        effective_type = step_type if step_type in persona else "crud"
        return persona.get(effective_type, "")
    
    # All other subdomains: simple string (same for all step types)
    return persona


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


def get_contextual_examples(
    subdomain: str, 
    step_description: str, 
    prev_subdomain: str | None = None,
    step_type: str = "crud"
) -> str:
    """
    Get contextual examples based on step verb and cross-domain patterns.
    
    Args:
        subdomain: Current step's subdomain
        step_description: Natural language step description
        prev_subdomain: Previous step's subdomain (for cross-domain patterns)
        step_type: "crud", "analyze", or "generate"
    
    Returns:
        1-2 relevant examples as markdown
    """
    desc_lower = step_description.lower()
    examples = []
    
    # === ANALYZE STEP GUIDANCE ===
    if step_type == "analyze":
        return _get_analyze_guidance(subdomain, desc_lower, prev_subdomain)
    
    # === GENERATE STEP GUIDANCE ===
    if step_type == "generate":
        return _get_generate_guidance(subdomain, desc_lower)
    
    # === SHOPPING PATTERNS ===
    if subdomain == "shopping":
        # Smart shopping pattern (check before adding)
        if any(verb in desc_lower for verb in ["add", "create", "save", "insert"]):
            examples.append("""**Smart Add Pattern** (check existing first):
1. `db_read` shopping_list to check what's already there
2. In analyze step or your reasoning: merge duplicates, consolidate quantities
3. `db_create` only NEW items, `db_update` existing quantities if needed""")
        
        # Cross-domain: from recipes
        if prev_subdomain == "recipes":
            examples.append("""**Recipe → Shopping Pattern**:
Previous step read recipe ingredients. Use those IDs/names to add to shopping list.
Normalize names: "diced tomatoes" → "tomatoes".""")
        
        # Cross-domain: from meal_plan
        if prev_subdomain == "meal_plan":
            examples.append("""**Meal Plan → Shopping Pattern**:
Previous step read meal plan. For each recipe_id, you may need to read recipe_ingredients, then add to shopping.""")
    
    # === RECIPE PATTERNS ===
    elif subdomain == "recipes":
        # Linked table create
        if any(verb in desc_lower for verb in ["create", "save", "add"]):
            examples.append("""**Create Recipe Pattern** (linked tables):
1. `db_create` on `recipes` → get the new `id` from response
2. `db_create` on `recipe_ingredients` with that `recipe_id`
3. `step_complete` only after BOTH are done""")
        
        # Linked table delete
        if any(verb in desc_lower for verb in ["delete", "remove", "clear"]):
            examples.append("""**Delete Recipe Pattern** (FK-safe order):
1. `db_delete` on `recipe_ingredients` WHERE recipe_id = X
2. `db_delete` on `recipes` WHERE id = X
Delete children first, then parent.""")
        
        # Search
        if any(verb in desc_lower for verb in ["find", "search", "look"]):
            examples.append("""**Recipe Search** (use OR for keywords):
```json
{"tool": "db_read", "params": {"table": "recipes", "or_filters": [
  {"field": "name", "op": "ilike", "value": "%chicken%"},
  {"field": "name", "op": "ilike", "value": "%curry%"}
], "limit": 10}}
```""")
    
    # === MEAL PLAN PATTERNS ===
    elif subdomain == "meal_plan":
        if any(verb in desc_lower for verb in ["create", "add", "save", "plan"]):
            examples.append("""**Add to Meal Plan**:
```json
{"tool": "db_create", "params": {"table": "meal_plans", "data": {
  "date": "2025-01-02", "meal_type": "dinner", "recipe_id": "<uuid>", "servings": 2
}}}
```
If recipe doesn't exist, suggest creating it first.""")
    
    # === INVENTORY PATTERNS ===
    elif subdomain == "inventory":
        if any(verb in desc_lower for verb in ["add", "create"]):
            examples.append("""**Add to Inventory**:
```json
{"tool": "db_create", "params": {"table": "inventory", "data": {
  "name": "eggs", "quantity": 12, "unit": "pieces", "location": "fridge"
}}}
```
Normalize names and add location/category tags.""")
    
    # === TASKS PATTERNS ===
    elif subdomain == "tasks":
        if any(verb in desc_lower for verb in ["create", "add", "remind"]):
            examples.append("""**Create Task** (link to meal plan if applicable):
```json
{"tool": "db_create", "params": {"table": "tasks", "data": {
  "title": "Thaw chicken", "due_date": "2025-01-02", "category": "prep",
  "meal_plan_id": "<uuid>"
}}}
```
Prefer meal_plan_id over recipe_id when possible.""")
    
    if not examples:
        return ""
    
    return "## Patterns for This Step\n\n" + "\n\n".join(examples)


def _get_analyze_guidance(subdomain: str, desc_lower: str, prev_subdomain: str | None) -> str:
    """Get guidance for analyze steps based on subdomain and context."""
    
    guidance_parts = ["## Analysis Guidance\n"]
    
    # === RECIPES ANALYZE ===
    if subdomain == "recipes":
        if "preference" in desc_lower or "fit" in desc_lower or "match" in desc_lower or "enough" in desc_lower:
            guidance_parts.append("""**Matching Recipes to Preferences:**
- Check dietary_restrictions and allergies — these are HARD constraints (must exclude)
- Check available_equipment — only suggest recipes using equipment they have
- Check time_budget_minutes — respect their time constraints
- Check cuisine_preferences — prioritize their favorite cuisines
- Check skill_level — match recipe complexity to their skill

**Flag gaps explicitly:** If the request needs N meals but you only found M matching recipes (M < N), say so clearly:
- "Found 1 matching recipe for 5 requested meals — need 4 more recipes"
- This helps downstream steps know to generate new recipes

**Output format:**
```json
{"matching_recipes": [{"recipe_id": "...", "name": "...", "fit_score": "high/medium", "notes": "..."}], 
 "excluded_recipes": [{"recipe_id": "...", "name": "...", "reason": "requires wok (not available)"}],
 "gap": {"requested": 5, "found": 1, "need_new": 4}}
```""")
        else:
            guidance_parts.append("""**Recipe Analysis:**
Output a structured analysis with clear recommendations. Include recipe IDs for downstream steps.
If analyzing for meal planning, flag any gaps between what's needed and what's available.""")
    
    # === SHOPPING ANALYZE ===
    elif subdomain == "shopping":
        if "missing" in desc_lower or "need" in desc_lower or "inventory" in desc_lower:
            guidance_parts.append("""**Finding Missing Ingredients:**
1. Compare recipe ingredients (from step N) against inventory (from step M)
2. Also check current shopping list to avoid duplicates
3. Output the delta — what's needed but not in inventory AND not already on shopping list

**Output format:**
```json
{"missing_items": [{"name": "chicken breast", "quantity": 2, "unit": "lbs", "from_recipe": "Butter Chicken"}],
 "already_have": ["rice", "garlic", "onion"],
 "already_on_list": ["tomatoes"]}
```""")
        else:
            guidance_parts.append("""**Shopping Analysis:**
Compare lists and output clear deltas. Normalize ingredient names (strip prep states).""")
    
    # === MEAL PLAN ANALYZE ===
    elif subdomain == "meal_plan":
        if "recipe" in desc_lower or "fit" in desc_lower:
            guidance_parts.append("""**Analyzing Recipes for Meal Plan:**
1. Look at previous step's recipes and preferences
2. Consider variety (don't repeat cuisines back-to-back)
3. Consider schedule (quick meals on busy days, elaborate on weekends)
4. Output recipe assignments with dates and meal types

**Output format:**
```json
{"recommended_assignments": [
  {"date": "2025-01-06", "meal_type": "dinner", "recipe_id": "...", "recipe_name": "...", "reason": "Quick weeknight option"}
]}
```""")
        elif "prep" in desc_lower or "task" in desc_lower:
            guidance_parts.append("""**Identifying Prep Tasks:**
Look at meal plans and identify what needs advance prep:
- Marinating (needs 2-24 hours)
- Thawing frozen ingredients
- Batch cooking components
- Soaking (beans, grains)

**Output format:**
```json
{"prep_tasks": [{"task": "Thaw chicken", "for_meal": "Monday dinner", "due_by": "Sunday evening", "meal_plan_id": "..."}]}
```""")
    
    # === INVENTORY ANALYZE ===
    elif subdomain == "inventory":
        if "expir" in desc_lower:
            guidance_parts.append("""**Expiring Items Analysis:**
Prioritize by urgency. Group by category. Include usage suggestions.

**Output format:**
```json
{"urgent": [{"name": "milk", "expires": "2025-01-02", "suggestion": "Use in breakfast smoothies"}],
 "this_week": [...]}
```""")
    
    # General guidance if nothing specific matched
    if len(guidance_parts) == 1:
        guidance_parts.append(f"""**General Analysis:**
- Review data from previous steps carefully
- Output structured JSON in `data` field
- Include IDs where relevant for downstream CRUD steps
- Be specific and actionable""")
    
    return "\n\n".join(guidance_parts)


def _get_generate_guidance(subdomain: str, desc_lower: str) -> str:
    """Get guidance for generate steps based on subdomain."""
    
    guidance_parts = ["## Generation Guidance\n"]
    
    # === RECIPES GENERATE ===
    if subdomain == "recipes":
        guidance_parts.append("""**Recipe Structure:**
Generate complete recipe with ALL required fields:
```json
{
  "recipe": {
    "name": "Spicy Garlic Shrimp Pasta",
    "description": "A quick weeknight pasta...",
    "instructions": "1. Cook pasta...\\n2. Sauté shrimp...",
    "cuisine": "Italian",
    "difficulty": "easy",
    "prep_time_minutes": 10,
    "cook_time_minutes": 20,
    "servings": 4,
    "tags": ["weeknight", "quick", "seafood"]
  },
  "ingredients": [
    {"name": "shrimp", "quantity": 1, "unit": "lb", "notes": "peeled and deveined"},
    {"name": "pasta", "quantity": 8, "unit": "oz"},
    {"name": "garlic", "quantity": 4, "unit": "cloves", "notes": "minced"}
  ]
}
```
**Important:** Include BOTH `recipe` and `ingredients` — they'll be saved together.""")
    
    # === MEAL PLAN GENERATE ===
    elif subdomain == "meal_plan":
        guidance_parts.append("""**Meal Plan Structure:**
Generate entries with dates, meal types, and recipe references:
```json
{
  "meal_plan": [
    {"date": "2025-01-06", "meal_type": "breakfast", "recipe_id": "abc123", "recipe_name": "Overnight Oats", "servings": 2},
    {"date": "2025-01-06", "meal_type": "lunch", "notes": "Leftovers from Sunday"},
    {"date": "2025-01-06", "meal_type": "dinner", "recipe_id": "def456", "recipe_name": "Butter Chicken", "servings": 4}
  ]
}
```
**recipe_id is optional** — use it if referencing saved recipes. For "leftovers" or "eating out", just add notes.
**Use recipe IDs from previous step** if recipes were read/analyzed earlier.""")
    
    # === TASKS GENERATE ===
    elif subdomain == "tasks":
        guidance_parts.append("""**Task Structure:**
```json
{
  "tasks": [
    {"title": "Thaw chicken for Tuesday", "due_date": "2025-01-06", "category": "prep", "meal_plan_id": "..."},
    {"title": "Buy wine for date night", "due_date": "2025-01-08", "category": "shopping"}
  ]
}
```
Categories: prep, shopping, cleanup, other""")
    
    # General guidance if nothing specific matched
    if len(guidance_parts) == 1:
        guidance_parts.append("""**General Generation:**
- Use user profile to personalize content
- Output structured JSON that can be saved in the next step
- Include all required fields for the target table""")
    
    return "\n\n".join(guidance_parts)


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
    "recipes": "",
    "shopping": "",
    "meal_plan": """
**Note**: Meal plans are cooking sessions (what to cook on what day). For reminders like "thaw chicken" or "buy wine", use the `tasks` subdomain instead.
""",
    "tasks": """
**Note**: Tasks are freeform to-dos. They can optionally link to a meal_plan or recipe, but don't have to.
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

Get this week's meals: `{"tool": "db_read", "params": {"table": "meal_plans", "filters": [{"field": "date", "op": ">=", "value": "2025-01-01"}, {"field": "date", "op": "<=", "value": "2025-01-07"}]}}`

Add to meal plan: `{"tool": "db_create", "params": {"table": "meal_plans", "data": {"recipe_id": "<recipe-uuid>", "date": "2025-01-02", "meal_type": "dinner", "servings": 2}}}`

**Batch cooking session** (making stock, prep bases):
```json
{"tool": "db_create", "params": {"table": "meal_plans", "data": {"date": "2025-01-05", "meal_type": "other", "notes": "Make chicken stock for the week"}}}
```

**Note**: Each row is a meal/cooking session on a date. For reminders/to-dos, use the `tasks` subdomain instead.
""",
    "tasks": """## Examples

Get pending tasks: `{"tool": "db_read", "params": {"table": "tasks", "filters": [{"field": "completed", "op": "=", "value": false}]}}`

Create freeform reminder: `{"tool": "db_create", "params": {"table": "tasks", "data": {"title": "Buy new chef's knife", "category": "shopping"}}}`

Create task linked to meal plan:
```json
{"tool": "db_create", "params": {"table": "tasks", "data": {"title": "Thaw chicken", "due_date": "2025-01-06", "category": "prep", "meal_plan_id": "<meal-plan-uuid>"}}}
```

Create task linked to recipe:
```json
{"tool": "db_create", "params": {"table": "tasks", "data": {"title": "Prep mise en place", "due_date": "2025-01-06", "category": "prep", "recipe_id": "<recipe-uuid>"}}}
```

Mark task complete: `{"tool": "db_update", "params": {"table": "tasks", "filters": [{"field": "id", "op": "=", "value": "<task-uuid>"}], "data": {"completed": true}}}`
""",
    "preferences": """## Examples

Get preferences: `{"tool": "db_read", "params": {"table": "preferences", "filters": [], "limit": 1}}`

**Update planning rhythm (how they want to cook):**
```json
{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"planning_rhythm": ["weekends only", "30min weeknights"]}}}
```

**Update current vibes (culinary interests):**
```json
{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"current_vibes": ["more vegetables", "fusion experiments", "soup skills"]}}}
```

**Update hard constraints:**
```json
{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"dietary_restrictions": ["vegetarian"], "allergies": ["peanuts"]}}}
```

**Update equipment:**
```json
{"tool": "db_update", "params": {"table": "preferences", "filters": [], "data": {"available_equipment": ["instant-pot", "air-fryer"]}}}
```
""",
    "history": """## Examples

Log a cooked meal:
```json
{"tool": "db_create", "params": {"table": "cooking_log", "data": {
  "recipe_id": "<recipe-uuid>",
  "servings": 4,
  "rating": 5,
  "notes": "Came out great! Added extra garlic."
}}}
```

Get recent cooking history: `{"tool": "db_read", "params": {"table": "cooking_log", "filters": [], "limit": 10}}`

Get cooking log for specific recipe:
```json
{"tool": "db_read", "params": {"table": "cooking_log", "filters": [
  {"field": "recipe_id", "op": "=", "value": "<recipe-uuid>"}
]}}
```

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

**🔗 LINKED TABLES: `recipes` ↔ `recipe_ingredients`**

Any write (create/update/delete) must touch BOTH tables:
- `recipes` — parent (has `id`)
- `recipe_ingredients` — children (linked by `recipe_id`)

Order: Create parent→children. Delete children→parent.

**⚠️ Don't assume data hygiene — always check/modify both tables, even if one returns empty.**

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

**⚠️ Smart Shopping List Updates:**
When adding ingredients from recipes/meal plans:
1. **Read first** — Check what's already on the shopping list
2. **Combine duplicates** — If "olive oil" is already listed, don't add a second row
3. **Update quantities** — For countable items (2 eggs + 3 eggs = 5 eggs), increase quantity
4. **Keep separate for staples** — Bottles/jars (soy sauce, olive oil) often don't need quantity math

Pattern: `db_read` → merge in analyze step → `db_create` new items + `db_update` existing quantities

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
| household_size | integer | Yes (default 1) ← For portioning |
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

