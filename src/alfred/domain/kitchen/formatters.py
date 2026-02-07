"""
Kitchen Domain Formatters.

Contains all kitchen-specific formatting logic that was previously
scattered across reply.py, injection.py, and act.py.

Phase 3a: Extracted from core files to isolate kitchen domain knowledge.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from alfred.core.id_registry import SessionIdRegistry


# =============================================================================
# Empty Responses (from reply.py)
# =============================================================================

EMPTY_RESPONSES: dict[str, str] = {
    "inventory": "Your pantry is empty. Want me to help you add some items?",
    "shopping": "Your shopping list is empty.",
    "recipes": "No recipes saved yet. Want me to suggest some?",
    "tasks": "No tasks on your list.",
    "meal_plans": "No meal plans scheduled.",
    "preferences": "No preferences set yet.",
}


# =============================================================================
# Table Format Protocols (from injection.py)
# =============================================================================

# Define how each table should be formatted for LLM consumption
# Format: {table: {primary: str, details: [str], show_id: bool}}
TABLE_FORMAT_PROTOCOLS: dict[str, dict[str, Any]] = {
    "inventory": {
        "primary": "name",
        "details": ["quantity", "location", "expiry_date"],
        "ingredient_details": ["parent_category", "family", "tier"],
        "show_id": True,
    },
    "shopping_list": {
        "primary": "name",
        "details": ["quantity", "unit", "category"],
        "ingredient_details": ["parent_category", "family", "tier"],
        "show_id": True,
    },
    "recipes": {
        "primary": "name",
        "details": ["cuisine", "total_time", "servings", "occasions", "health_tags", "source_url"],
        "show_id": True,
        "format": "recipe",
    },
    "recipe_ingredients": {
        "primary": "name",
        "details": ["quantity", "unit", "notes", "is_optional"],
        "show_id": False,
        "group_by": "recipe_id",
    },
    "meal_plans": {
        "primary": "date",
        "details": ["meal_type", "recipe_id", "notes", "servings"],
        "show_id": True,
        "format": "meal_plan",
    },
    "tasks": {
        "primary": "title",
        "details": ["due_date", "status", "category"],
        "show_id": True,
    },
    "preferences": {
        "primary": None,
        "details": ["dietary_restrictions", "allergies", "favorite_cuisines", "cooking_skill_level"],
        "show_id": False,
        "format": "key_value",
    },
}


# =============================================================================
# Strip Fields
# =============================================================================

# Fields to strip from injection context (internal noise for LLM)
INJECTION_STRIP_FIELDS = {"user_id", "created_at", "updated_at", "ingredient_id"}

# Fields to strip from reply output (internal/technical)
REPLY_STRIP_FIELDS = {
    "id", "user_id", "ingredient_id", "recipe_id", "meal_plan_id",
    "parent_recipe_id", "created_at", "updated_at", "is_purchased",
}


# =============================================================================
# Record Formatters (from injection.py)
# =============================================================================


def format_meal_plan_record(record: dict, protocol: dict) -> str:
    """
    Format a meal plan record: date [slot] -> recipe (servings) notes id:meal_1

    Examples:
    - 2026-01-12 [lunch] -> Butter Chicken (recipe_1) (servings: 2) id:meal_1
    - 2026-01-13 [dinner] -> recipe_2 (servings: 1) notes:"Leftovers from lunch" id:meal_2
    - 2026-01-14 [other] -> notes:"Make chicken stock" (servings: 4) id:meal_3
    """
    date = record.get("date", "no-date")
    meal_type = record.get("meal_type", "meal")
    recipe_ref = record.get("recipe_id")
    notes = record.get("notes")
    servings = record.get("servings")
    meal_id = record.get("id", "")

    # Try to get enriched recipe name
    recipe_label = record.get("_recipe_id_label")

    # Determine main content: recipe or notes-only
    if recipe_ref:
        if recipe_label:
            content = f"{recipe_label} ({recipe_ref})"
        else:
            content = recipe_ref
    elif notes:
        content = f'notes:"{notes}"'
    else:
        content = "no-recipe"

    parts = [f"  - {date} [{meal_type}] \u2192 {content}"]

    if servings:
        parts.append(f"(servings: {servings})")

    if notes and recipe_ref:
        parts.append(f'notes:"{notes}"')

    if meal_id:
        parts.append(f"id:{meal_id}")

    return " ".join(parts)


def format_recipe_record(record: dict, protocol: dict) -> str:
    """
    Format a recipe record with grouped ingredients.

    Output format:
    ```
    recipe_1 (Chicken Tikka):
      cuisine: indian | time: 45min | servings: 4
      occasions: weeknight | health: high-protein
      proteins: chicken
      vegetables: onion, bell pepper
      dairy: yogurt
      spices: garam masala, turmeric
      [instructions: 8 steps]  # only if present
    ```
    """
    lines = []

    name = record.get("name", "Recipe")
    recipe_id = record.get("id", "")
    lines.append(f"  {recipe_id} ({name}):")

    # Core metadata
    meta_parts = []
    if record.get("cuisine"):
        meta_parts.append(f"cuisine: {record['cuisine']}")

    prep = record.get("prep_time_minutes") or record.get("prep_time")
    cook = record.get("cook_time_minutes") or record.get("cook_time")
    total = record.get("total_time")
    if total:
        meta_parts.append(f"time: {total}")
    elif prep or cook:
        time_str = f"{prep or 0}+{cook or 0}min"
        meta_parts.append(f"time: {time_str}")

    if record.get("servings"):
        meta_parts.append(f"servings: {record['servings']}")
    if record.get("difficulty"):
        meta_parts.append(f"difficulty: {record['difficulty']}")

    if meta_parts:
        lines.append(f"    {' | '.join(meta_parts)}")

    # Tags
    tag_parts = []
    if record.get("occasions"):
        tag_parts.append(f"occasions: {', '.join(record['occasions'][:3])}")
    if record.get("health_tags"):
        tag_parts.append(f"health: {', '.join(record['health_tags'][:3])}")
    if record.get("flavor_tags"):
        tag_parts.append(f"flavor: {', '.join(record['flavor_tags'][:2])}")
    if record.get("equipment_tags"):
        tag_parts.append(f"equipment: {', '.join(record['equipment_tags'][:2])}")

    if tag_parts:
        lines.append(f"    {' | '.join(tag_parts)}")

    # Ingredients grouped by category
    ingredients = record.get("recipe_ingredients", [])
    if ingredients:
        by_category: dict[str, list[str]] = defaultdict(list)
        for ing in ingredients:
            cat = ing.get("category") or "other"
            name = ing.get("name", "?")
            by_category[cat].append(name)

        category_order = [
            "proteins", "vegetables", "produce", "fruits", "dairy", "cheese",
            "grains", "rice", "pasta", "pantry", "canned", "spices",
            "cuisine_indian", "cuisine_thai", "cuisine_mexican", "other",
        ]

        displayed_cats: set[str] = set()
        for cat in category_order:
            if cat in by_category:
                names = by_category[cat]
                unique_names = list(dict.fromkeys(names))
                lines.append(f"    {cat}: {', '.join(unique_names)}")
                displayed_cats.add(cat)

        for cat, names in by_category.items():
            if cat not in displayed_cats:
                unique_names = list(dict.fromkeys(names))
                lines.append(f"    {cat}: {', '.join(unique_names)}")

    # Instructions
    instructions = record.get("instructions")
    if instructions:
        if isinstance(instructions, list):
            lines.append(f"    [instructions: {len(instructions)} steps]")
        else:
            lines.append(f"    [instructions: included]")

    return "\n".join(lines)


# =============================================================================
# Recipe Data Formatter for Act Context (from act.py)
# =============================================================================


def format_recipe_data(
    ref: str,
    label: str,
    data: dict,
    registry: SessionIdRegistry | None = None,
) -> list[str]:
    """Format recipe data for Act context - includes key fields and instruction count.

    Checks what data is available and labels appropriately:
    - Full: has instructions AND full ingredients (with id, quantity)
    - Snapshot: missing instructions OR only ingredient names

    When registry is provided, ingredient refs are looked up and displayed inline.
    """
    has_instructions = bool(data.get("instructions"))
    ingredients = data.get("recipe_ingredients", [])

    has_full_ingredients = False
    if ingredients and isinstance(ingredients[0], dict):
        has_full_ingredients = "id" in ingredients[0] or "quantity" in ingredients[0]

    missing = []
    if not has_instructions:
        missing.append("instructions")
    if not has_full_ingredients and ingredients:
        missing.append("ingredient details")

    if missing:
        snapshot_indicator = f" *(snapshot \u2014 missing: {', '.join(missing)})*"
    else:
        snapshot_indicator = ""

    lines = [f"### `{ref}`: {label} (recipe){snapshot_indicator}"]

    # Core metadata
    meta = []
    if data.get("cuisine"):
        meta.append(f"cuisine: {data['cuisine']}")
    prep = data.get("prep_time_minutes") or data.get("prep_time")
    cook = data.get("cook_time_minutes") or data.get("cook_time")
    total = data.get("total_time")
    if total:
        meta.append(f"time: {total}")
    elif prep or cook:
        time_str = f"{prep or 0}+{cook or 0}min"
        meta.append(f"time: {time_str}")
    if data.get("servings"):
        meta.append(f"servings: {data['servings']}")
    if data.get("difficulty"):
        meta.append(f"difficulty: {data['difficulty']}")
    if meta:
        lines.append(f"  {' | '.join(meta)}")

    # Tags
    tags = []
    if data.get("occasions"):
        tags.append(f"occasions: {', '.join(data['occasions'][:3])}")
    if data.get("health_tags"):
        tags.append(f"health: {', '.join(data['health_tags'][:3])}")
    if tags:
        lines.append(f"  {' | '.join(tags)}")

    # Ingredients
    if ingredients:
        if has_full_ingredients:
            lines.append(f"  **ingredients ({len(ingredients)} items):**")
            for ing in ingredients:
                qty = ing.get("quantity", "")
                unit = ing.get("unit", "")
                name = ing.get("name", "?")
                qty_str = f"{qty} {unit} " if qty else ""

                ing_ref = None
                if registry and ing.get("id"):
                    ing_ref = registry.get_ref(str(ing["id"]))

                if ing_ref:
                    lines.append(f"    - `{ing_ref}`: {qty_str}{name}")
                else:
                    lines.append(f"    - {qty_str}{name}")
        else:
            names = [i.get("name", "?") for i in ingredients[:5]]
            more = f"... ({len(ingredients)} total)" if len(ingredients) > 5 else f" ({len(ingredients)} total)"
            lines.append(f"  ingredients (names only): {', '.join(names)}{more}")

    # Instructions
    instructions = data.get("instructions")
    if instructions:
        if isinstance(instructions, list):
            lines.append(f"  **instructions ({len(instructions)} steps):**")
            for i, step in enumerate(instructions, 1):
                if re.match(r'^\d+\.?\s', step):
                    lines.append(f"    {step}")
                else:
                    lines.append(f"    {i}. {step}")
        else:
            lines.append(f"  **instructions:** {instructions}")
    else:
        lines.append("  instructions: not loaded")

    return lines


# =============================================================================
# Quick Response Formatters (from reply.py)
# =============================================================================


def format_inventory_summary(items: list) -> str:
    """Format inventory items for display."""
    if not items:
        return EMPTY_RESPONSES["inventory"]

    lines = ["Here's what's in your pantry:\n"]

    by_location: dict[str, list] = {}
    for item in items:
        loc = item.get("location", "other") or "other"
        if loc not in by_location:
            by_location[loc] = []
        by_location[loc].append(item)

    for location, loc_items in by_location.items():
        if len(by_location) > 1:
            lines.append(f"\n**{location.title()}:**")
        for item in loc_items:
            name = item.get("name", "Unknown")
            qty = item.get("quantity", "")
            unit = item.get("unit", "")
            qty_str = f" ({qty} {unit})" if qty else ""
            lines.append(f"- {name}{qty_str}")

    return "\n".join(lines)


def format_recipe_summary(recipes: list) -> str:
    """Format recipe list for display."""
    if not recipes:
        return EMPTY_RESPONSES["recipes"]

    lines = [f"You have {len(recipes)} recipe{'s' if len(recipes) > 1 else ''} saved:\n"]

    for recipe in recipes[:20]:
        name = recipe.get("name", "Untitled")
        cuisine = recipe.get("cuisine", "")
        cuisine_str = f" ({cuisine})" if cuisine else ""
        lines.append(f"- **{name}**{cuisine_str}")

    if len(recipes) > 20:
        lines.append(f"\n...and {len(recipes) - 20} more.")

    return "\n".join(lines)


def format_shopping_summary(items: list) -> str:
    """Format shopping list for display."""
    if not items:
        return EMPTY_RESPONSES["shopping"]

    lines = [f"Your shopping list ({len(items)} item{'s' if len(items) > 1 else ''}):\n"]

    for item in items:
        name = item.get("name", "Unknown")
        qty = item.get("quantity", "")
        unit = item.get("unit", "")
        qty_str = f" ({qty} {unit})" if qty else ""
        checked = "\u2611" if item.get("checked") else "\u2610"
        lines.append(f"{checked} {name}{qty_str}")

    return "\n".join(lines)


def format_task_summary(tasks: list) -> str:
    """Format task list for display."""
    if not tasks:
        return EMPTY_RESPONSES["tasks"]

    lines = [f"Your tasks ({len(tasks)}):\n"]

    for task in tasks:
        desc = task.get("description", "No description")
        done = "\u2713" if task.get("completed") else "\u25cb"
        lines.append(f"{done} {desc}")

    return "\n".join(lines)


def format_meal_plan_summary(plans: list) -> str:
    """Format meal plan list for display."""
    if not plans:
        return EMPTY_RESPONSES["meal_plans"]

    lines = [f"Your meal plans ({len(plans)} scheduled):\n"]

    by_date: dict[str, list] = {}
    for plan in plans:
        date = plan.get("date", "Unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(plan)

    for date, date_plans in sorted(by_date.items()):
        lines.append(f"\n**{date}:**")
        for plan in date_plans:
            meal_type = plan.get("meal_type", "meal")
            notes = plan.get("notes", "")
            lines.append(f"- {meal_type.title()}: {notes or '(no details)'}")

    return "\n".join(lines)


# =============================================================================
# Record Formatting for Reply (from reply.py)
# =============================================================================


def format_records_for_reply(
    records: list[dict], table_type: str | None, indent: int = 2
) -> str | None:
    """
    Kitchen-specific record formatting for user-facing reply display.

    Handles special cases: preferences as key-value, recipes with full
    instructions, meal plans with recipe links.

    Returns None for table types that should use generic formatting.
    """
    if not records:
        return None

    prefix = " " * indent

    # Preferences: key-value display
    if table_type == "preferences":
        lines = []
        for record in records:
            clean = {k: v for k, v in record.items() if k not in REPLY_STRIP_FIELDS and v is not None}
            lines.append(f"{prefix}Your Preferences:")
            for field in [
                "dietary_restrictions", "allergies", "favorite_cuisines",
                "cooking_skill_level", "available_equipment",
                "household_adults", "household_kids", "household_babies",
                "planning_rhythm", "current_vibes", "nutrition_goals",
                "disliked_ingredients",
            ]:
                value = clean.get(field)
                if value is not None and value != [] and value != "":
                    label = field.replace("_", " ").title()
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    lines.append(f"{prefix}  - {label}: {value}")
        return "\n".join(lines)

    # Recipes: special formatting with optional full display
    if table_type == "recipes":
        lines = []
        for record in records:
            clean = {k: v for k, v in record.items() if k not in REPLY_STRIP_FIELDS and v is not None}
            name = clean.get("name") or clean.get("title") or "(untitled recipe)"
            parts = [f"{prefix}- {name}"]

            if clean.get("cuisine"):
                parts.append(f"({clean['cuisine']})")
            if clean.get("total_time"):
                parts.append(f"{clean['total_time']}min")
            if clean.get("servings"):
                parts.append(f"serves {clean['servings']}")
            if clean.get("tags"):
                tags = clean["tags"][:3] if isinstance(clean["tags"], list) else []
                if tags:
                    parts.append(f"[{', '.join(tags)}]")

            # Full recipe display when instructions are present
            if clean.get("instructions"):
                lines.append(" ".join(parts))
                if clean.get("description"):
                    lines.append(f"{prefix}  *{clean['description']}*")

                ingredients = clean.get("recipe_ingredients", [])
                if ingredients:
                    lines.append(f"{prefix}  **Ingredients:**")
                    for ing in ingredients[:20]:
                        if isinstance(ing, dict):
                            ing_name = ing.get("name", "")
                            qty = ing.get("quantity", "")
                            unit = ing.get("unit", "")
                            notes = ing.get("notes", "")
                            ing_str = f"{prefix}    - {ing_name}"
                            if qty:
                                ing_str += f" ({qty}"
                                if unit:
                                    ing_str += f" {unit}"
                                ing_str += ")"
                            if notes:
                                ing_str += f", {notes}"
                            lines.append(ing_str)

                instructions = clean.get("instructions", [])
                if instructions:
                    lines.append(f"{prefix}  **Instructions:**")
                    for i, step in enumerate(instructions[:15], 1):
                        lines.append(f"{prefix}    {i}. {step}")
            else:
                lines.append(" ".join(parts))

        return "\n".join(lines)

    # Meal plans: date + meal type + recipe link
    if table_type == "meal_plans":
        lines = []
        for record in records:
            clean = {k: v for k, v in record.items() if k not in REPLY_STRIP_FIELDS and v is not None}
            name = clean.get("date") or clean.get("name") or "(no date)"
            parts = [f"{prefix}- {name}"]

            if clean.get("meal_type"):
                parts.append(f"[{clean['meal_type']}]")
            recipe_label = clean.get("_recipe_id_label")
            has_recipe = recipe_label or clean.get("recipe_id")
            if recipe_label:
                parts.append(f"\u2192 {recipe_label}")
            elif clean.get("recipe_id"):
                parts.append(f"\u2192 recipe:{clean['recipe_id']}")
            elif clean.get("notes"):
                notes_preview = clean["notes"][:50] + "..." if len(clean["notes"]) > 50 else clean["notes"]
                parts.append(f'notes:"{notes_preview}"')
            if clean.get("servings"):
                parts.append(f"({clean['servings']} servings)")
            if clean.get("notes") and has_recipe:
                notes_preview = clean["notes"][:50] + "..." if len(clean["notes"]) > 50 else clean["notes"]
                parts.append(f'notes:"{notes_preview}"')

            lines.append(" ".join(parts))

        return "\n".join(lines)

    # Not a kitchen-specific table type — return None for generic formatting
    return None
