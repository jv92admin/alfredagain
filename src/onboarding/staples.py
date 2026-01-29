"""
Staples Selection for Onboarding.

Shows a curated set of tier-1 pantry essentials that users typically keep
stocked. Selected items are seeded into the user's inventory at onboarding
completion so Alfred has immediate context (cold-start fix).
"""

import logging
import uuid as _uuid

logger = logging.getLogger(__name__)

# Parent categories that qualify as "staples" (shelf-stable essentials)
STAPLE_CATEGORIES = ["pantry", "spices", "grains", "baking", "dairy"]

# Dietary restriction → exclusion rules (family values are lowercase, singular)
DIETARY_EXCLUSIONS: dict[str, dict[str, list[str]]] = {
    "vegan": {
        "parent_categories": ["dairy"],
        "families": ["honey", "gelatin"],
    },
    "vegetarian": {
        "parent_categories": [],
        "families": ["anchovy", "fish sauce"],
    },
    "dairy-free": {
        "parent_categories": ["dairy"],
        "families": [],
    },
    "gluten-free": {
        "parent_categories": [],
        "families": [
            "flour", "wheat", "pasta", "bread",
            "noodles", "couscous", "barley",
        ],
    },
    "pescatarian": {
        "parent_categories": [],
        "families": [],
    },
}

# Cap on essentials returned
MAX_ESSENTIALS = 40


def _compute_exclusions(
    dietary_restrictions: list[str],
) -> dict[str, set[str]]:
    """Merge all exclusion rules for the user's dietary restrictions."""
    excluded_categories: set[str] = set()
    excluded_families: set[str] = set()
    for restriction in dietary_restrictions:
        rules = DIETARY_EXCLUSIONS.get(restriction.lower(), {})
        excluded_categories.update(rules.get("parent_categories", []))
        excluded_families.update(rules.get("families", []))
    return {"categories": excluded_categories, "families": excluded_families}


def _is_excluded(row: dict, excluded: dict[str, set[str]]) -> bool:
    """Check if an ingredient should be excluded based on dietary rules."""
    if row.get("parent_category") in excluded["categories"]:
        return True
    if row.get("family") in excluded["families"]:
        return True
    return False


async def get_staples_options(
    cuisines: list[str] | None = None,
    dietary_restrictions: list[str] | None = None,
) -> dict:
    """
    Get curated staple essentials for the onboarding checklist.

    Args:
        cuisines: User's selected cuisines (for highlighting cuisine-specific items)
        dietary_restrictions: User's dietary restrictions (for filtering)

    Returns:
        {
            "essentials": [
                {"id": "uuid", "name": "salt", "default_unit": "container",
                 "parent_category": "spices", "cuisine_match": false},
                ...
            ],
            "pre_selected_ids": ["uuid1", ...],       # All essentials
            "cuisine_suggested_ids": ["uuid3", ...]    # Tier 2 cuisine matches
        }
    """
    from alfred.db.client import get_service_client

    client = get_service_client()
    cuisines = cuisines or []
    dietary_restrictions = dietary_restrictions or []
    cuisines_lower = [c.lower() for c in cuisines]
    excluded = _compute_exclusions(dietary_restrictions)

    try:
        # Fetch tier 1 ingredients from staple categories only
        result = client.table("ingredients").select(
            "id, name, parent_category, family, tier, cuisines, default_unit"
        ).in_(
            "tier", [1, 2]
        ).in_(
            "parent_category", STAPLE_CATEGORIES
        ).execute()

        if not result.data:
            logger.warning("No tier 1/2 staple ingredients found")
            return {"essentials": [], "pre_selected_ids": [], "cuisine_suggested_ids": []}

        # Apply dietary restriction filtering
        items = [row for row in result.data if not _is_excluded(row, excluded)]

        # Sort: tier 1 first, then cuisine-matched tier 2, then remaining tier 2
        # Within each group, sort alphabetically
        def sort_key(ing: dict) -> tuple:
            tier = ing.get("tier", 2)
            name = ing.get("name", "").lower()
            ing_cuisines = ing.get("cuisines") or []
            is_cuisine_match = any(
                c in cuisines_lower for c in [x.lower() for x in ing_cuisines]
            )
            if tier == 1:
                return (0, name)
            elif is_cuisine_match:
                return (1, name)
            else:
                return (2, name)

        items.sort(key=sort_key)
        items = items[:MAX_ESSENTIALS]

        # Build response
        essentials = []
        pre_selected_ids = []
        cuisine_suggested_ids = []

        for ing in items:
            tier = ing.get("tier", 2)
            ing_cuisines = ing.get("cuisines") or []
            is_cuisine_match = any(
                c in cuisines_lower for c in [x.lower() for x in ing_cuisines]
            )

            ingredient_data = {
                "id": str(ing["id"]),
                "name": ing["name"],
                "default_unit": ing.get("default_unit"),
                "parent_category": ing.get("parent_category"),
            }

            if is_cuisine_match and tier == 2:
                ingredient_data["cuisine_match"] = True
                cuisine_suggested_ids.append(str(ing["id"]))

            essentials.append(ingredient_data)
            pre_selected_ids.append(str(ing["id"]))

        return {
            "essentials": essentials,
            "pre_selected_ids": pre_selected_ids,
            "cuisine_suggested_ids": cuisine_suggested_ids,
        }

    except Exception as e:
        logger.error(f"Failed to get staples options: {e}")
        return {"essentials": [], "pre_selected_ids": [], "cuisine_suggested_ids": []}


def validate_staple_selections(ingredient_ids: list[str]) -> list[str]:
    """
    Validate that ingredient IDs are valid UUIDs.

    Args:
        ingredient_ids: List of ingredient ID strings

    Returns:
        List of valid UUID strings (invalid ones filtered out)
    """
    valid_ids = []
    for id_str in ingredient_ids:
        try:
            _uuid.UUID(id_str)
            valid_ids.append(id_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid ingredient ID skipped: {id_str}")

    return valid_ids
