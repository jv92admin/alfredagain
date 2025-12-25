"""
Alfred V2 - Name Normalization.

Utilities for normalizing user input for consistent matching.
"""

import re


def normalize_name(name: str) -> str:
    """
    Normalize a name for consistent matching.

    Operations:
    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse multiple spaces to single space

    Args:
        name: Raw name input

    Returns:
        Normalized name

    Examples:
        normalize_name("  Chicken Thighs  ") -> "chicken thighs"
        normalize_name("TOMATO") -> "tomato"
        normalize_name("green   pepper") -> "green pepper"
    """
    return " ".join(name.lower().strip().split())


def normalize_for_search(query: str) -> str:
    """
    Normalize a search query.

    Same as normalize_name but also removes common filler words.

    Args:
        query: Search query

    Returns:
        Normalized query
    """
    normalized = normalize_name(query)

    # Remove common filler words for search
    filler_words = {"a", "an", "the", "some", "any"}
    words = normalized.split()
    filtered = [w for w in words if w not in filler_words]

    return " ".join(filtered) if filtered else normalized


def clean_unit(unit: str) -> str:
    """
    Clean and normalize a unit string.

    Args:
        unit: Raw unit input (e.g., "LBS", "Pounds", "lb")

    Returns:
        Normalized unit (lowercase, singular form where applicable)
    """
    unit = unit.lower().strip()

    # Common unit aliases - map to standard form
    unit_aliases = {
        "pounds": "lb",
        "pound": "lb",
        "lbs": "lb",
        "ounces": "oz",
        "ounce": "oz",
        "grams": "g",
        "gram": "g",
        "kilograms": "kg",
        "kilogram": "kg",
        "liters": "l",
        "liter": "l",
        "litres": "l",
        "litre": "l",
        "milliliters": "ml",
        "milliliter": "ml",
        "cups": "cup",
        "tablespoons": "tbsp",
        "tablespoon": "tbsp",
        "teaspoons": "tsp",
        "teaspoon": "tsp",
        "pieces": "piece",
        "items": "item",
    }

    return unit_aliases.get(unit, unit)


def extract_quantity_unit(text: str) -> tuple[float | None, str | None, str]:
    """
    Extract quantity and unit from a text string.

    Args:
        text: Text like "3 lbs of chicken" or "2 cups flour"

    Returns:
        Tuple of (quantity, unit, remaining_text)
        Returns (None, None, text) if no quantity found

    Examples:
        "3 lbs chicken" -> (3.0, "lb", "chicken")
        "chicken" -> (None, None, "chicken")
        "1/2 cup flour" -> (0.5, "cup", "flour")
    """
    text = text.strip()

    # Pattern for quantity (including fractions)
    # Put fractions first so they match before whole numbers
    quantity_pattern = r"^(\d+/\d+|\d+(?:\.\d+)?)\s*"
    match = re.match(quantity_pattern, text)

    if not match:
        return (None, None, text)

    qty_str = match.group(1)
    remaining = text[match.end() :].strip()

    # Parse quantity (handle fractions)
    if "/" in qty_str:
        parts = qty_str.split("/")
        quantity = float(parts[0]) / float(parts[1])
    else:
        quantity = float(qty_str)

    # Try to extract unit
    unit_pattern = r"^(\w+)\s*(?:of\s+)?(.*)$"
    unit_match = re.match(unit_pattern, remaining, re.IGNORECASE)

    if unit_match:
        potential_unit = unit_match.group(1).lower()
        # Check if it looks like a unit
        known_units = {
            "lb",
            "lbs",
            "oz",
            "g",
            "kg",
            "cup",
            "cups",
            "tbsp",
            "tsp",
            "ml",
            "l",
            "piece",
            "pieces",
            "item",
            "items",
            "pound",
            "pounds",
            "ounce",
            "ounces",
            "gram",
            "grams",
            "gallon",
            "gallons",
            "pint",
            "pints",
            "quart",
            "quarts",
            "carton",
            "cartons",
            "bottle",
            "bottles",
            "can",
            "cans",
            "bag",
            "bags",
            "box",
            "boxes",
            "bunch",
            "bunches",
            "head",
            "heads",
            "clove",
            "cloves",
        }
        if potential_unit in known_units:
            return (quantity, clean_unit(potential_unit), unit_match.group(2).strip())

    return (quantity, None, remaining)

