"""Ingredient Parser - Transform raw ingredient strings to structured data.

Uses gpt-4.1-mini to parse messy ingredient strings into:
- ingredient_name: Canonical name for DB matching
- quantity: Numeric amount
- unit: Measurement unit
- notes: Preparation instructions, size modifiers, qualifiers
- is_optional: Whether marked as optional/garnish
"""

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from alfred.config import settings
from alfred.tools.schema import get_table_schema

logger = logging.getLogger(__name__)


@dataclass
class ParsedIngredient:
    """Parsed ingredient with structured fields."""

    raw: str
    ingredient_name: str
    quantity: float | None
    unit: str | None
    notes: str | None
    is_optional: bool


async def _build_schema_context() -> str:
    """Fetch recipe_ingredients schema dynamically for prompt injection."""
    try:
        schema = await get_table_schema("recipe_ingredients")
        columns = schema.get("columns", [])

        if not columns:
            # Fallback if schema fetch fails
            return """Fields: name (str), quantity (numeric), unit (str), notes (str), is_optional (bool)"""

        # Format relevant columns for the prompt
        relevant = ["name", "quantity", "unit", "notes", "is_optional"]
        col_info = []
        for col in columns:
            if col["name"] in relevant:
                col_info.append(f"- {col['name']}: {col['type']}")

        return "\n".join(col_info)
    except Exception as e:
        logger.warning(f"Failed to fetch schema, using fallback: {e}")
        return """Fields: name (str), quantity (numeric), unit (str), notes (str), is_optional (bool)"""


def _build_parsing_prompt(raw_ingredients: list[str], schema_context: str) -> str:
    """Build the parsing prompt with dynamic schema."""
    ingredients_list = "\n".join(f"- {ing}" for ing in raw_ingredients)

    return f"""Parse these recipe ingredients into structured data.

Target schema fields:
{schema_context}

For each ingredient, extract:
- ingredient_name: The canonical ingredient (singular, no modifiers, no prep)
- quantity: Numeric amount (convert fractions: 1/2 → 0.5, null if none)
- unit: Measurement unit if present (cup, tbsp, lb, clove, etc.)
- notes: ALL preparation instructions, size modifiers, and qualifiers
  Examples: "peeled and minced", "medium, boiled", "fresh, torn", "to taste"
- is_optional: ONLY true if EXPLICITLY marked as optional in the text

CRITICAL rules for is_optional:
- "to taste" does NOT mean optional - salt "to taste" is still required, just flexible amount
- "for garnish" alone does NOT mean optional - only if it says "optional garnish" or "if desired"
- ONLY mark as optional when text explicitly says: "optional", "if desired", "optionally", "for serving (optional)"
- When in doubt, is_optional should be FALSE

CRITICAL: Don't lose prep context!
- "peeled garlic" → ingredient_name: "garlic", notes: "peeled"
- "boiled potatoes" → ingredient_name: "potato", notes: "boiled"
- "2 cloves garlic, minced" → ingredient_name: "garlic", quantity: 2, unit: "clove", notes: "minced"
- "salt, to taste" → ingredient_name: "salt", notes: "to taste", is_optional: false
- "parsley for garnish (optional)" → ingredient_name: "parsley", notes: "for garnish", is_optional: true

Ingredients to parse:
{ingredients_list}

Output as JSON array:
[
  {{"raw": "original string", "ingredient_name": "garlic", "quantity": 2, "unit": "clove", "notes": "peeled and minced", "is_optional": false}},
  ...
]

Output ONLY valid JSON, no other text."""


async def parse_ingredients_batch(
    raw_ingredients: list[str],
) -> list[ParsedIngredient]:
    """
    Parse multiple raw ingredient strings in one LLM call.

    Args:
        raw_ingredients: List of raw ingredient strings from scraper

    Returns:
        List of ParsedIngredient with structured data
    """
    if not raw_ingredients:
        return []

    # Filter out empty strings
    raw_ingredients = [ing.strip() for ing in raw_ingredients if ing.strip()]
    if not raw_ingredients:
        return []

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Get dynamic schema for prompt
    schema_context = await _build_schema_context()
    prompt = _build_parsing_prompt(raw_ingredients, schema_context)

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=3000,
        )

        content = response.choices[0].message.content.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            # Extract content between code fences
            lines = content.split("\n")
            # Remove first line (```json) and last line (```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        parsed_data = json.loads(content)

        results = []
        for item in parsed_data:
            results.append(
                ParsedIngredient(
                    raw=item.get("raw", ""),
                    ingredient_name=item.get("ingredient_name", ""),
                    quantity=item.get("quantity"),
                    unit=item.get("unit"),
                    notes=item.get("notes"),
                    is_optional=item.get("is_optional", False),
                )
            )

        logger.info(f"Parsed {len(results)} ingredients successfully")
        return results

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response: {e}")
        # Fallback: return raw strings as-is
        return [
            ParsedIngredient(
                raw=ing,
                ingredient_name=ing,
                quantity=None,
                unit=None,
                notes=None,
                is_optional=False,
            )
            for ing in raw_ingredients
        ]
    except Exception as e:
        logger.error(f"Ingredient parsing failed: {e}")
        # Fallback: return raw strings as-is
        return [
            ParsedIngredient(
                raw=ing,
                ingredient_name=ing,
                quantity=None,
                unit=None,
                notes=None,
                is_optional=False,
            )
            for ing in raw_ingredients
        ]


async def parse_and_link_ingredients(
    raw_ingredients: list[str],
) -> list[dict]:
    """
    Parse ingredients and link to master ingredients database.

    Args:
        raw_ingredients: List of raw ingredient strings

    Returns:
        List of dicts ready for recipe_ingredients table with ingredient_id
    """
    from alfred.tools.ingredient_lookup import lookup_ingredient

    # Parse raw strings
    parsed = await parse_ingredients_batch(raw_ingredients)

    # Link to master ingredients DB
    results = []
    for p in parsed:
        # Skip empty ingredients
        if not p.ingredient_name.strip():
            continue

        # Try to find matching ingredient in DB
        match = None
        try:
            match = await lookup_ingredient(p.ingredient_name, operation="write")
        except Exception as e:
            logger.warning(f"Ingredient lookup failed for '{p.ingredient_name}': {e}")

        results.append(
            {
                "name": p.ingredient_name,
                "quantity": p.quantity,
                "unit": p.unit,
                "notes": p.notes,
                "is_optional": p.is_optional,
                "ingredient_id": match.id if match else None,
                "match_confidence": match.confidence if match else 0,
                "raw_text": p.raw,
            }
        )

    return results
