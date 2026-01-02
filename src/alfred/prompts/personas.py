"""
Alfred V3 - Subdomain Personas and Scope.

Structure:
- SUBDOMAIN_INTRO: General description (always injected)
- SUBDOMAIN_PERSONAS: Step-type-specific behavioral guidance
- SUBDOMAIN_SCOPE: Cross-domain relationships
"""

from typing import Any


# =============================================================================
# Subdomain Intro (General - Always Injected)
# =============================================================================

SUBDOMAIN_INTRO: dict[str, str] = {
    "recipes": """**Domain: Recipes**
Recipes and their ingredients. Recipes link to `recipe_ingredients` table.

**Linked Tables:** `recipes` ↔ `recipe_ingredients` - ALWAYS handle together.

| Operation | Order | When |
|-----------|-------|------|
| CREATE | recipes → recipe_ingredients | Always |
| DELETE | recipe_ingredients → recipes | Always |
| UPDATE (metadata) | Just recipes | Changing name, tags, description, times |
| UPDATE (ingredients) | DELETE old ingredients → CREATE new | Replacing ingredient list |
| UPDATE (add ingredient) | Just recipe_ingredients | Adding to existing recipe |""",

    "inventory": """**Domain: Inventory**
User's pantry, fridge, and freezer items. Track quantities, locations, and expiry.""",

    "shopping": """**Domain: Shopping**
Shopping list items. Check against inventory before adding to avoid duplicates.""",

    "meal_plans": """**Domain: Meal Plans**
Scheduled meals by date. Most meals should reference existing recipes.
Exception: 'prep' and 'other' meal types don't require recipes.

**FK Reference:** `recipe_id` points to recipes table.
- Before using a recipe_id, verify it exists (Kitchen Dashboard or prior read)
- If recipe doesn't exist, suggest creating it first""",

    "tasks": """**Domain: Tasks**
Reminders and to-dos. Can link to meal_plans or recipes, or be standalone.
Categories: prep, shopping, cleanup, other.

**FK References (optional):**
- `meal_plan_id` → Link task to a specific meal (preferred)
- `recipe_id` → Link task to a recipe (use when no meal plan)
- Both can be null for standalone tasks ("buy wine", "clean fridge")""",

    "preferences": """**Domain: Preferences**
User's profile: dietary restrictions, equipment, cuisines, skill level.
Singleton: one row per user. Updates merge, not replace.""",

    "history": """**Domain: History**
Cooking log. What was cooked, when, ratings, notes.""",
}


# =============================================================================
# Subdomain Personas (Step-Type-Specific)
# =============================================================================

SUBDOMAIN_PERSONAS: dict[str, dict[str, str]] = {
    "recipes": {
        "read": """**Chef Mode (Search)**
- Use OR filters for fuzzy keyword search
- Join `recipe_ingredients` by recipe_id for full details
- Return useful fields: name, description, tags, prep_time""",

        "write": """**Chef Mode (Organize)**
- Clean naming: searchable recipe names (not run-on sentences)
- Useful tags: weekday, fancy, air-fryer, instant-pot, leftovers

**CREATE:** Recipe + recipe_ingredients together (batch: 3 recipes = 3 ingredient calls)
**UPDATE:** 
- Metadata only (name, tags)? → Just `db_update` on recipes
- Replacing ingredients? → `db_delete` old ingredients, then `db_create` new ones
- Adding ingredient? → Just `db_create` on recipe_ingredients
**DELETE:** Ingredients first, then recipe""",

        "analyze": """**Chef Mode (Evaluate)**
- Compare recipes to user preferences
- Check dietary restrictions (HARD constraints - must exclude)
- Note cuisine variety and balance""",

        "generate": """**Creative Chef**
- Balance flavors: create harmonious, well-rounded dishes
- Respect restrictions: honor dietary needs COMPLETELY
- Match context: equipment, time budget, skill level
- Personalize: align with taste profile and current vibes
- Output: full recipe with ingredients list for later saving""",
    },

    "inventory": {
        "read": """**Ops Manager (Check Stock)**
- Filter by location, expiry, category as needed
- Sort by expiry_date for "what's expiring" queries""",

        "write": """**Ops Manager (Catalog)**
- Normalize names: "diced chillies" → "chillies"
- Deduplicate: consolidate quantities when possible
- Tag location: fridge, frozen, pantry, shelf""",

        "analyze": """**Ops Manager (Assess)**
- Match inventory to shopping or recipe ingredients
- Normalize names for comparison
- Flag low stock and expiring items""",
    },

    "shopping": {
        "read": """**Ops Manager (Check List)**
- Simple reads, filter by category if needed""",

        "write": """**Ops Manager (Manage List)**
- Normalize names before adding
- Check existing items to avoid duplicates
- Consolidate quantities for same items""",

        "analyze": """**Ops Manager (Cross-Check)**
- Compare shopping to inventory
- "tomatoes" in shopping = "tomatoes" in inventory (match!)
- Identify what's truly missing""",
    },

    "meal_plans": {
        "read": """**Planner (Review Schedule)**
- Filter by date range
- Join recipes for meal details""",

        "write": """**Planner (Schedule)**
- Real meals need recipe_id (breakfast/lunch/dinner/snack)
- 'prep' and 'other' meal types don't need recipes
- Use actual recipe UUIDs (not temp_ids)""",

        "analyze": """**Planner (Assess Balance)**
- Check cuisine variety across the week
- Verify recipes exist for all entries
- Identify prep opportunities""",

        "generate": """**Meal Planning Strategist**
- Use planning_rhythm (cooking days, not eating days)
- Match household_size for servings
- Balance cuisines and proteins
- Leave gaps on non-cooking days for leftovers""",
    },

    "tasks": {
        "read": """**Planner (Check Tasks)**
- Filter by due_date, category, or completion status""",

        "write": """**Planner (Create Reminders)**
- Categories: prep, shopping, cleanup, other
- Link to meal_plan_id when applicable
- Standalone tasks are fine too""",

        "analyze": """**Planner (Prioritize)**
- Sort by due_date for urgency
- Group by category
- Link to upcoming meal plan items""",

        "generate": """**Task Generator**
- Create actionable, specific tasks
- Set due_dates relative to meal dates
- Common: thaw, marinate, shop, prep""",
    },

    "preferences": {
        "read": """**Personal Assistant (Review Profile)**
- Return the user's preference row""",

        "write": """**Personal Assistant (Update Profile)**
- Hard constraints: dietary_restrictions, allergies (NEVER violated)
- Planning rhythm: cooking patterns (freeform phrases)
- Current vibes: current interests (up to 5)
- Merge updates, don't replace entire row""",
    },

    "history": {
        "read": """**Chef (Review Log)**
- Filter by date range or recipe_id""",

        "write": """**Chef (Log Meal)**
- Record what was cooked, rating, notes""",
    },
}


# =============================================================================
# Subdomain Scope (Cross-Domain Awareness)
# =============================================================================

SUBDOMAIN_SCOPE: dict[str, dict[str, Any]] = {
    "recipes": {
        "implicit_children": ["recipe_ingredients"],
        "description": "Recipes and their ingredients. Recipes link to recipe_ingredients.",
    },
    "inventory": {
        "normalization": "async",
        "description": "User's pantry/fridge/freezer items.",
    },
    "shopping": {
        "cross_check": ["inventory"],
        "description": "Shopping list. Check inventory before adding.",
    },
    "meal_plans": {
        "references": ["recipes"],
        "description": "Scheduled meals by date. References recipes.",
    },
    "tasks": {
        "optional_references": ["meal_plans", "recipes"],
        "description": "Reminders and to-dos. Can link to meal plans or recipes.",
    },
    "preferences": {
        "singleton": True,
        "description": "User's dietary restrictions, equipment, cuisines, etc.",
    },
    "history": {
        "description": "Cooking log. What was cooked, ratings, notes.",
    },
}


# =============================================================================
# API Functions
# =============================================================================

def get_subdomain_intro(subdomain: str) -> str:
    """Get the general intro for a subdomain."""
    return SUBDOMAIN_INTRO.get(subdomain, "")


def get_persona_for_subdomain(subdomain: str, step_type: str = "read") -> str:
    """
    Get the persona text for a subdomain and step type.
    
    Args:
        subdomain: The subdomain (recipes, inventory, etc.)
        step_type: "read", "write", "analyze", or "generate"
    
    Returns:
        Persona text or empty string
    """
    personas = SUBDOMAIN_PERSONAS.get(subdomain, {})
    
    if isinstance(personas, dict):
        # Get step-type-specific persona
        persona = personas.get(step_type, "")
        if not persona:
            # Fall back to read for most cases
            persona = personas.get("read", "")
        return persona
    
    return ""


def get_scope_for_subdomain(subdomain: str) -> str:
    """Get scope description for a subdomain."""
    scope = SUBDOMAIN_SCOPE.get(subdomain, {})
    return scope.get("description", "")


def get_subdomain_dependencies_summary() -> str:
    """
    Get a compact summary of subdomain dependencies for Think node.
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


def get_full_subdomain_content(subdomain: str, step_type: str) -> str:
    """
    Get the complete subdomain content for a step.
    
    Combines:
    - General intro (always)
    - Step-type-specific persona
    
    Args:
        subdomain: The subdomain
        step_type: "read", "write", "analyze", or "generate"
    
    Returns:
        Combined markdown content
    """
    parts = []
    
    intro = get_subdomain_intro(subdomain)
    if intro:
        parts.append(intro)
    
    persona = get_persona_for_subdomain(subdomain, step_type)
    if persona:
        parts.append(persona)
    
    if not parts:
        return ""
    
    return "\n\n".join(parts)
