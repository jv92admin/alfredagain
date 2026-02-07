"""
Alfred V3 - Ingredient Resolver Layer.

STATUS: DORMANT STUB - Not wired up. Delete if no use case by April 2026.

This module was created during the ingredient enrichment work (Jan 2026) but
turned out to be unnecessary because:
1. The LLM already extracts qty/unit/name before calling CRUD
2. Recipe import has its own LLM parser (recipe_import/ingredient_parser.py)
3. enrich_with_ingredient_id() in ingredient_lookup.py handles DB matching

See: docs/specs/ingredient-enrichment.md for context.

---

Parses free-form ingredient text into structured data:
- Quantity and unit extraction
- Modifier detection (preparation, state, quality)
- Ingredient name matching via ingredient_lookup

Example:
    "2 lbs boneless skinless chicken thighs"
    -> {
        "ingredient_id": "uuid...",
        "ingredient_name": "chicken thigh",
        "quantity": 2.0,
        "unit": "lbs",
        "modifiers": ["boneless", "skinless"],
        "confidence": 0.95,
        "match_type": "fuzzy"
    }
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from alfred.domain.kitchen.tools.ingredient_lookup import lookup_ingredient, IngredientMatch

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Common units with their variations
UNITS = {
    # Volume
    "cup": ["cup", "cups", "c", "c."],
    "tablespoon": ["tablespoon", "tablespoons", "tbsp", "tbsp.", "tbs", "tbs.", "T"],
    "teaspoon": ["teaspoon", "teaspoons", "tsp", "tsp.", "t"],
    "fluid ounce": ["fluid ounce", "fluid ounces", "fl oz", "fl. oz.", "fl oz."],
    "pint": ["pint", "pints", "pt", "pt."],
    "quart": ["quart", "quarts", "qt", "qt."],
    "gallon": ["gallon", "gallons", "gal", "gal."],
    "milliliter": ["milliliter", "milliliters", "ml", "mL"],
    "liter": ["liter", "liters", "l", "L"],

    # Weight
    "pound": ["pound", "pounds", "lb", "lbs", "lb.", "lbs."],
    "ounce": ["ounce", "ounces", "oz", "oz."],
    "gram": ["gram", "grams", "g", "g."],
    "kilogram": ["kilogram", "kilograms", "kg", "kg."],

    # Count/Container
    "piece": ["piece", "pieces", "pc", "pcs"],
    "slice": ["slice", "slices"],
    "can": ["can", "cans"],
    "jar": ["jar", "jars"],
    "bottle": ["bottle", "bottles"],
    "package": ["package", "packages", "pkg", "pkgs"],
    "bag": ["bag", "bags"],
    "box": ["box", "boxes"],
    "container": ["container", "containers"],
    "bunch": ["bunch", "bunches"],
    "head": ["head", "heads"],
    "stalk": ["stalk", "stalks"],
    "sprig": ["sprig", "sprigs"],
    "clove": ["clove", "cloves"],
    "ear": ["ear", "ears"],  # corn
    "stick": ["stick", "sticks"],  # butter
    "whole": ["whole"],
    "large": ["large", "lg"],
    "medium": ["medium", "med"],
    "small": ["small", "sm"],
}

# Build reverse lookup: variation -> canonical unit
UNIT_LOOKUP = {}
for canonical, variations in UNITS.items():
    for var in variations:
        UNIT_LOOKUP[var.lower()] = canonical

# Modifiers by category
MODIFIERS = {
    "preparation": [
        "diced", "minced", "chopped", "sliced", "cubed", "shredded",
        "julienned", "chiffonade", "brunoise", "grated", "crushed",
        "mashed", "pureed", "blended", "ground", "crumbled",
        "halved", "quartered", "whole", "peeled", "trimmed",
    ],
    "state": [
        "raw", "cooked", "roasted", "grilled", "fried", "sauteed",
        "steamed", "poached", "braised", "baked", "broiled",
        "fresh", "frozen", "canned", "dried", "dehydrated",
        "pickled", "smoked", "cured", "marinated",
    ],
    "quality": [
        "boneless", "skinless", "bone-in", "skin-on",
        "organic", "grass-fed", "free-range", "wild-caught",
        "extra virgin", "cold-pressed", "unfiltered",
        "low-sodium", "unsalted", "salted", "sweetened", "unsweetened",
    ],
    "size": [
        "large", "medium", "small", "extra large", "extra-large",
        "thick", "thin", "bite-size", "bite-sized",
    ],
    "ripeness": [
        "ripe", "unripe", "overripe", "green", "firm", "soft",
    ],
}

# Flatten modifiers for quick lookup
ALL_MODIFIERS = set()
for category_mods in MODIFIERS.values():
    ALL_MODIFIERS.update(mod.lower() for mod in category_mods)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ResolvedIngredient:
    """Result of ingredient resolution."""
    # Matched ingredient info
    ingredient_id: str | None = None
    ingredient_name: str | None = None
    match_type: Literal["exact", "fuzzy", "semantic", "none"] = "none"
    confidence: float = 0.0

    # Parsed quantity and unit
    quantity: float | None = None
    unit: str | None = None

    # Extracted modifiers
    modifiers: list[str] = field(default_factory=list)

    # Original input for reference
    original_text: str = ""

    # Cleaned ingredient text used for matching
    cleaned_name: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "ingredient_id": self.ingredient_id,
            "ingredient_name": self.ingredient_name,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "quantity": self.quantity,
            "unit": self.unit,
            "modifiers": self.modifiers,
            "original_text": self.original_text,
            "cleaned_name": self.cleaned_name,
        }


# =============================================================================
# Parsing Functions
# =============================================================================

def _extract_quantity(text: str) -> tuple[float | None, str]:
    """
    Extract quantity from the beginning of ingredient text.

    Handles:
    - Integers: "2 cups"
    - Decimals: "1.5 lbs"
    - Fractions: "1/2 cup", "1 1/2 cups"
    - Unicode fractions: "½ cup"

    Returns:
        Tuple of (quantity, remaining_text)
    """
    text = text.strip()

    # Unicode fraction map
    unicode_fractions = {
        "½": 0.5, "⅓": 1/3, "⅔": 2/3, "¼": 0.25, "¾": 0.75,
        "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8,
        "⅙": 1/6, "⅚": 5/6, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
    }

    # Replace unicode fractions
    for ufrac, value in unicode_fractions.items():
        if ufrac in text:
            # Check if preceded by integer (e.g., "1½")
            match = re.match(rf'^(\d+)\s*{ufrac}', text)
            if match:
                whole = int(match.group(1))
                return whole + value, text[match.end():].strip()
            # Just the fraction
            idx = text.index(ufrac)
            if idx == 0 or not text[idx-1].isdigit():
                return value, text[idx+1:].strip()

    # Pattern: "1 1/2" or "1-1/2" (mixed number)
    mixed_pattern = r'^(\d+)\s*[-\s]?\s*(\d+)\s*/\s*(\d+)'
    match = re.match(mixed_pattern, text)
    if match:
        whole = int(match.group(1))
        num = int(match.group(2))
        denom = int(match.group(3))
        return whole + (num / denom), text[match.end():].strip()

    # Pattern: "1/2" (simple fraction)
    frac_pattern = r'^(\d+)\s*/\s*(\d+)'
    match = re.match(frac_pattern, text)
    if match:
        num = int(match.group(1))
        denom = int(match.group(2))
        return num / denom, text[match.end():].strip()

    # Pattern: decimal or integer
    num_pattern = r'^(\d+(?:\.\d+)?)'
    match = re.match(num_pattern, text)
    if match:
        return float(match.group(1)), text[match.end():].strip()

    return None, text


def _extract_unit(text: str) -> tuple[str | None, str]:
    """
    Extract unit from the beginning of text.

    Returns:
        Tuple of (canonical_unit, remaining_text)
    """
    text = text.strip()
    text_lower = text.lower()

    # Try to match units (longest match first)
    best_match = None
    best_length = 0

    for variation, canonical in UNIT_LOOKUP.items():
        if text_lower.startswith(variation):
            # Check it's a word boundary (not "cups" matching "c" in "chicken")
            if len(variation) > best_length:
                # Ensure word boundary after unit
                after_idx = len(variation)
                if after_idx >= len(text) or not text[after_idx].isalnum():
                    best_match = canonical
                    best_length = len(variation)

    if best_match:
        return best_match, text[best_length:].strip()

    return None, text


def _extract_modifiers(text: str) -> tuple[list[str], str]:
    """
    Extract modifiers from ingredient text.

    Returns:
        Tuple of (list_of_modifiers, remaining_text)
    """
    words = text.lower().split()
    modifiers = []
    remaining_words = []

    i = 0
    while i < len(words):
        word = words[i]

        # Check for two-word modifiers (e.g., "extra virgin", "bone-in")
        if i + 1 < len(words):
            two_word = f"{word} {words[i+1]}"
            if two_word in ALL_MODIFIERS:
                modifiers.append(two_word)
                i += 2
                continue

        # Check single word
        if word in ALL_MODIFIERS:
            modifiers.append(word)
        else:
            remaining_words.append(words[i] if i < len(text.split()) else word)

        i += 1

    # Reconstruct remaining text with original casing
    remaining = " ".join(remaining_words)
    return modifiers, remaining


def _clean_ingredient_name(text: str) -> str:
    """
    Clean up ingredient name for matching.

    Removes:
    - Parenthetical notes
    - Extra whitespace
    - Leading/trailing punctuation
    """
    # Remove parenthetical content
    text = re.sub(r'\([^)]*\)', '', text)

    # Remove common filler words at start
    filler_words = ["a", "an", "the", "some", "about", "approximately", "roughly"]
    words = text.split()
    while words and words[0].lower() in filler_words:
        words.pop(0)

    text = " ".join(words)

    # Clean up whitespace and punctuation
    text = re.sub(r'\s+', ' ', text)
    text = text.strip(' ,.-')

    return text


# =============================================================================
# Main Resolver Function
# =============================================================================

async def resolve_ingredient(
    text: str,
    use_semantic: bool = True,
) -> ResolvedIngredient:
    """
    Resolve a free-form ingredient string into structured data.

    Args:
        text: Raw ingredient text (e.g., "2 lbs boneless skinless chicken thighs")
        use_semantic: Whether to use semantic matching as fallback

    Returns:
        ResolvedIngredient with parsed quantity, unit, modifiers, and matched ingredient
    """
    original = text
    result = ResolvedIngredient(original_text=original)

    # Step 1: Extract quantity
    quantity, text = _extract_quantity(text)
    result.quantity = quantity

    # Step 2: Extract unit
    unit, text = _extract_unit(text)
    result.unit = unit

    # Step 3: Extract modifiers
    modifiers, text = _extract_modifiers(text)
    result.modifiers = modifiers

    # Step 4: Clean remaining text (the ingredient name)
    cleaned = _clean_ingredient_name(text)
    result.cleaned_name = cleaned

    if not cleaned:
        return result

    # Step 5: Look up ingredient
    match = await lookup_ingredient(
        cleaned,
        operation="write",
        use_semantic=use_semantic,
    )

    if match:
        result.ingredient_id = match.id
        result.ingredient_name = match.name
        result.match_type = match.match_type
        result.confidence = match.confidence

    return result


async def resolve_ingredients_batch(
    texts: list[str],
    use_semantic: bool = True,
) -> list[ResolvedIngredient]:
    """
    Resolve multiple ingredient strings.

    Args:
        texts: List of raw ingredient strings
        use_semantic: Whether to use semantic matching as fallback

    Returns:
        List of ResolvedIngredient objects
    """
    return [await resolve_ingredient(t, use_semantic) for t in texts]


# =============================================================================
# Utility Functions for CRUD Integration
# =============================================================================

async def resolve_and_enrich(
    data: dict,
    use_resolver: bool = True,
) -> dict:
    """
    Resolve ingredient from data['name'] and enrich the dict.

    Adds:
    - ingredient_id: matched ingredient UUID
    - modifiers: list of extracted modifiers (if schema supports)

    Args:
        data: Record dict with 'name' field
        use_resolver: Whether to use full resolver (vs simple lookup)

    Returns:
        Enriched data dict
    """
    name = data.get("name")
    if not name:
        return data

    # Skip if already has ingredient_id
    if data.get("ingredient_id"):
        return data

    resolved = await resolve_ingredient(name, use_semantic=True)

    enriched = {**data}

    if resolved.ingredient_id:
        enriched["ingredient_id"] = resolved.ingredient_id
        logger.info(
            f"Resolved '{name}' → '{resolved.ingredient_name}' "
            f"({resolved.match_type}, {resolved.confidence:.2f})"
        )

    # Store modifiers if extracted (caller decides whether to use)
    if resolved.modifiers:
        enriched["_modifiers"] = resolved.modifiers

    return enriched
