"""
Staples Selection for Onboarding.

Shows a curated set of ~40 pantry essentials ranked by anchor-list matching,
tier weight, and cuisine affinity. Selected items are seeded into the user's
inventory at onboarding completion so Alfred has immediate context (cold-start
fix).
"""

import logging
import uuid as _uuid

logger = logging.getLogger(__name__)

# Parent categories that qualify as "staples" (shelf-stable essentials)
STAPLE_CATEGORIES = ["pantry", "spices", "grains", "baking", "dairy"]

# Anchor names for universal pantry staples, split into two tiers.
# CORE anchors (things nearly every kitchen has) get a full boost.
# EXTRA anchors (common but not universal) get a smaller boost.
# Items not in either list can still appear via tier + cuisine scoring.
CORE_ANCHORS: set[str] = {
    "salt", "black pepper", "olive oil",
    "butter", "all-purpose flour",
    "granulated sugar", "rice", "pasta", "soy sauce", "vinegar",
    "baking powder", "baking soda", "garlic powder", "onion powder",
    "paprika", "cumin", "cinnamon", "oregano", "chili powder",
    "chicken broth", "canned tomatoes", "tomato paste", "tomato sauce",
    "vegetable oil", "canola oil", "honey", "brown sugar", "vanilla extract",
    "cornstarch", "milk", "eggs", "cheddar", "parmesan", "mozzarella",
}

EXTRA_ANCHORS: set[str] = {
    "sesame oil", "coconut oil", "white vinegar", "apple cider vinegar",
    "rice vinegar", "balsamic vinegar", "vegetable broth", "coconut milk",
    "peanut butter", "hot sauce", "dijon mustard", "ketchup", "mayonnaise",
    "Italian seasoning", "cayenne pepper", "turmeric", "smoked paprika",
    "bay leaves", "thyme", "red pepper flakes",
    "spaghetti", "bread", "oats", "rolled oats", "quinoa", "tortillas",
    "maple syrup", "cocoa powder", "powdered sugar",
    "yogurt", "cream cheese", "heavy cream", "sour cream",
    "worcestershire sauce", "flour",
}

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
MAX_ESSENTIALS = 60


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
    from alfred_kitchen.db.client import get_service_client

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

        # Build anchor lookups (lowercase for case-insensitive matching)
        core_lower = {a.lower() for a in CORE_ANCHORS}
        extra_lower = {a.lower() for a in EXTRA_ANCHORS}

        # Score each ingredient:
        #   anchor (0-0.5) + tier_weight (0.15) + cuisine_boost (0.1)
        # Core anchors get 0.5, extra anchors get 0.3, non-anchors get 0.
        cuisines_set = set(cuisines_lower)
        scored = []
        for ing in items:
            name_lower = ing.get("name", "").lower()
            if name_lower in core_lower:
                anchor_score = 0.5
            elif name_lower in extra_lower:
                anchor_score = 0.3
            else:
                anchor_score = 0.0
            tier_w = 1.0 if ing.get("tier") == 1 else 0.5
            ing_cuisines = {c.lower() for c in (ing.get("cuisines") or [])}
            cuisine_boost = 1.0 if cuisines_set & ing_cuisines else 0.0
            score = anchor_score + tier_w * 0.15 + cuisine_boost * 0.1
            scored.append((score, ing))

        scored.sort(key=lambda x: (-x[0], x[1].get("name", "").lower()))

        # Deduplicate by family: keep the highest-scored item per family.
        # Prevents "parmesan" + "parmesan cheese" or 3x olive oil variants.
        # Within each family, prefer anchor matches over non-anchors, then
        # shorter names (more generic) over longer ones.
        all_anchors = core_lower | extra_lower
        family_best: dict[str, dict] = {}
        for _score, ing in scored:
            family = (ing.get("family") or ing.get("name", "")).lower().strip()
            is_anchor = ing.get("name", "").lower() in all_anchors
            if family not in family_best:
                family_best[family] = ing
            else:
                prev = family_best[family]
                prev_anchor = prev.get("name", "").lower() in all_anchors
                # Prefer: anchor > non-anchor, then shorter name
                if is_anchor and not prev_anchor:
                    family_best[family] = ing
                elif is_anchor == prev_anchor and len(ing.get("name", "")) < len(prev.get("name", "")):
                    family_best[family] = ing

        # Re-score with deduped items
        deduped_set = set(id(v) for v in family_best.values())
        scored = [(s, ing) for s, ing in scored if id(ing) in deduped_set]

        items = [ing for _score, ing in scored[:MAX_ESSENTIALS]]

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
