"""
Cuisine Selection for Onboarding.

Simple multi-select for favorite cuisines.
No complex discovery needed - users know what cuisines they like.
"""


# Cuisine options with display metadata
CUISINE_OPTIONS = [
    {"id": "italian", "label": "Italian", "icon": "🇮🇹"},
    {"id": "mexican", "label": "Mexican", "icon": "🇲🇽"},
    {"id": "chinese", "label": "Chinese", "icon": "🇨🇳"},
    {"id": "japanese", "label": "Japanese", "icon": "🇯🇵"},
    {"id": "indian", "label": "Indian", "icon": "🇮🇳"},
    {"id": "thai", "label": "Thai", "icon": "🇹🇭"},
    {"id": "korean", "label": "Korean", "icon": "🇰🇷"},
    {"id": "vietnamese", "label": "Vietnamese", "icon": "🇻🇳"},
    {"id": "mediterranean", "label": "Mediterranean", "icon": "🫒"},
    {"id": "middle-eastern", "label": "Middle Eastern", "icon": "🧆"},
    {"id": "french", "label": "French", "icon": "🇫🇷"},
    {"id": "spanish", "label": "Spanish", "icon": "🇪🇸"},
    {"id": "greek", "label": "Greek", "icon": "🇬🇷"},
    {"id": "american", "label": "American", "icon": "🇺🇸"},
    {"id": "cajun", "label": "Cajun/Creole", "icon": "🦐"},
    {"id": "caribbean", "label": "Caribbean", "icon": "🏝️"},
    {"id": "ethiopian", "label": "Ethiopian", "icon": "🇪🇹"},
    {"id": "moroccan", "label": "Moroccan", "icon": "🇲🇦"},
    {"id": "turkish", "label": "Turkish", "icon": "🇹🇷"},
    {"id": "brazilian", "label": "Brazilian", "icon": "🇧🇷"},
]

VALID_CUISINE_IDS = {c["id"] for c in CUISINE_OPTIONS}

MAX_CUISINE_SELECTIONS = 7  # Reasonable limit


def get_cuisine_options() -> list[dict]:
    """Get all cuisine options for UI display."""
    return CUISINE_OPTIONS


def validate_cuisine_selections(selections: list[str]) -> list[str]:
    """
    Validate and cap cuisine selections.
    
    Args:
        selections: List of cuisine IDs
    
    Returns:
        Validated list (invalid removed, capped at max)
    """
    valid = []
    for s in selections:
        if s and s.lower().strip() in VALID_CUISINE_IDS:
            valid.append(s.lower().strip())
    
    return valid[:MAX_CUISINE_SELECTIONS]
