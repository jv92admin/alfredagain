"""
Staples Selection for Onboarding.

Shows ingredients grouped by parent_category, users select which ones
they always keep stocked. These are stored in preferences.assumed_staples
so Alfred knows what to assume is available.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Parent categories in display order
PARENT_CATEGORY_CONFIG = {
    "produce": {"label": "Produce", "icon": "🥬"},
    "protein": {"label": "Proteins", "icon": "🥩"},
    "dairy": {"label": "Dairy & Eggs", "icon": "🥛"},
    "grains": {"label": "Grains & Pasta", "icon": "🍚"},
    "pantry": {"label": "Pantry Essentials", "icon": "🫙"},
    "spices": {"label": "Spices & Seasonings", "icon": "🌶️"},
    "baking": {"label": "Baking", "icon": "🧁"},
    "specialty": {"label": "Specialty Items", "icon": "✨"},
}

# Display order for categories
CATEGORY_ORDER = [
    "pantry", "spices", "produce", "protein",
    "dairy", "grains", "baking", "specialty"
]

# Items to show per category (before "Show more")
ITEMS_PER_CATEGORY = 20


async def get_staples_options(cuisines: list[str] | None = None) -> dict:
    """
    Get staples options grouped by parent_category.

    Args:
        cuisines: User's selected cuisines (for highlighting cuisine-specific items)

    Returns:
        {
            "categories": [
                {
                    "id": "spices",
                    "label": "Spices & Seasonings",
                    "icon": "🌶️",
                    "ingredients": [
                        {"id": "uuid", "name": "salt", "tier": 1, "cuisine_match": false},
                        ...
                    ]
                },
                ...
            ],
            "pre_selected_ids": ["uuid1", "uuid2", ...],  # Tier 1 items
            "cuisine_suggested_ids": ["uuid3", ...]       # Tier 2 cuisine matches
        }
    """
    from alfred.db.client import get_service_client

    client = get_service_client()
    cuisines = cuisines or []
    cuisines_lower = [c.lower() for c in cuisines]

    try:
        # Fetch all tier 1 and tier 2 ingredients
        result = client.table("ingredients").select(
            "id, name, parent_category, family, tier, cuisines"
        ).in_("tier", [1, 2]).execute()

        if not result.data:
            logger.warning("No tier 1/2 ingredients found")
            return {"categories": [], "pre_selected_ids": [], "cuisine_suggested_ids": []}

        # Group by parent_category
        grouped = defaultdict(list)
        for row in result.data:
            parent_cat = row.get("parent_category") or "pantry"
            grouped[parent_cat].append(row)

        categories = []
        pre_selected_ids = []
        cuisine_suggested_ids = []

        for cat_id in CATEGORY_ORDER:
            if cat_id not in grouped:
                continue

            config = PARENT_CATEGORY_CONFIG.get(cat_id, {"label": cat_id.title(), "icon": "📦"})
            ingredients = grouped[cat_id]

            # Sort ingredients:
            # 1. Tier 1 first (alphabetical)
            # 2. Tier 2 cuisine-matched (alphabetical)
            # 3. Tier 2 remaining (alphabetical)
            def sort_key(ing):
                tier = ing.get("tier", 2)
                name = ing.get("name", "").lower()
                ing_cuisines = ing.get("cuisines") or []
                is_cuisine_match = any(c in cuisines_lower for c in [x.lower() for x in ing_cuisines])

                if tier == 1:
                    return (0, name)  # Tier 1 first
                elif is_cuisine_match:
                    return (1, name)  # Tier 2 cuisine match second
                else:
                    return (2, name)  # Tier 2 remaining last

            ingredients.sort(key=sort_key)

            # Limit to ITEMS_PER_CATEGORY
            ingredients = ingredients[:ITEMS_PER_CATEGORY]

            # Build ingredient list for response
            category_ingredients = []
            for ing in ingredients:
                tier = ing.get("tier", 2)
                ing_cuisines = ing.get("cuisines") or []
                is_cuisine_match = any(
                    c in cuisines_lower for c in [x.lower() for x in ing_cuisines]
                )

                ingredient_data = {
                    "id": str(ing["id"]),
                    "name": ing["name"],
                    "tier": tier,
                }

                # Mark cuisine matches
                if is_cuisine_match and tier == 2:
                    ingredient_data["cuisine_match"] = True
                    cuisine_suggested_ids.append(str(ing["id"]))

                # Track tier 1 for pre-selection
                if tier == 1:
                    pre_selected_ids.append(str(ing["id"]))

                category_ingredients.append(ingredient_data)

            if category_ingredients:
                categories.append({
                    "id": cat_id,
                    "label": config["label"],
                    "icon": config["icon"],
                    "ingredients": category_ingredients,
                })

        return {
            "categories": categories,
            "pre_selected_ids": pre_selected_ids,
            "cuisine_suggested_ids": cuisine_suggested_ids,
        }

    except Exception as e:
        logger.error(f"Failed to get staples options: {e}")
        return {"categories": [], "pre_selected_ids": [], "cuisine_suggested_ids": []}


def validate_staple_selections(ingredient_ids: list[str]) -> list[str]:
    """
    Validate that ingredient IDs are valid UUIDs.

    Args:
        ingredient_ids: List of ingredient ID strings

    Returns:
        List of valid UUID strings (invalid ones filtered out)
    """
    import uuid

    valid_ids = []
    for id_str in ingredient_ids:
        try:
            # Validate it's a proper UUID
            uuid.UUID(id_str)
            valid_ids.append(id_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid ingredient ID skipped: {id_str}")

    return valid_ids
