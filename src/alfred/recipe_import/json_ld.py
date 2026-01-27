"""JSON-LD/Schema.org extraction fallback."""

import logging

from .models import ExtractionMethod, ExtractionResult, RecipePreview
from .normalizer import (
    extract_image_url,
    extract_instructions_text,
    normalize_ingredients,
    parse_duration,
    parse_servings,
)

logger = logging.getLogger(__name__)


def extract_with_json_ld(url: str) -> ExtractionResult:
    """
    Extract recipe using JSON-LD/Schema.org structured data.

    This is a fallback for sites without custom scrapers but that
    have Schema.org Recipe markup.
    """
    try:
        import extruct
        import httpx
    except ImportError as e:
        logger.warning(f"extruct not installed: {e}")
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error="JSON-LD extraction library not available",
        )

    try:
        # Fetch the page
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)

        # Extract structured data
        data = extruct.extract(html, base_url=final_url, syntaxes=["json-ld", "microdata"])

        # Look for Recipe in JSON-LD
        recipe_data = _find_recipe_in_json_ld(data.get("json-ld", []))
        if not recipe_data:
            # Try microdata as fallback
            recipe_data = _find_recipe_in_microdata(data.get("microdata", []))

        if not recipe_data:
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.FAILED,
                error="No structured recipe data found on this page",
            )

        # Convert to RecipePreview
        name = recipe_data.get("name")
        if not name:
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.FAILED,
                error="Recipe data found but missing name",
            )

        preview = RecipePreview(
            name=name,
            source_url=final_url,
            description=recipe_data.get("description"),
            prep_time_minutes=parse_duration(recipe_data.get("prepTime")),
            cook_time_minutes=parse_duration(recipe_data.get("cookTime")),
            servings=parse_servings(recipe_data.get("recipeYield")),
            cuisine=_extract_cuisine(recipe_data),
            ingredients_raw=normalize_ingredients(recipe_data.get("recipeIngredient", [])),
            instructions=extract_instructions_text(recipe_data.get("recipeInstructions", [])),
            image_url=extract_image_url(recipe_data.get("image")),
        )

        return ExtractionResult(
            success=True,
            method=ExtractionMethod.JSON_LD,
            preview=preview,
        )

    except httpx.TimeoutException:
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error="Request timed out",
        )
    except httpx.HTTPStatusError as e:
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error=f"Failed to fetch page: HTTP {e.response.status_code}",
        )
    except Exception as e:
        logger.debug(f"JSON-LD extraction failed for {url}: {e}")
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error=str(e),
        )


def _find_recipe_in_json_ld(json_ld_items: list) -> dict | None:
    """Find Recipe schema in JSON-LD data."""
    for item in json_ld_items:
        if isinstance(item, dict):
            # Direct Recipe type
            item_type = item.get("@type", "")
            if item_type == "Recipe" or (isinstance(item_type, list) and "Recipe" in item_type):
                return item

            # Recipe inside @graph
            graph = item.get("@graph", [])
            for graph_item in graph:
                if isinstance(graph_item, dict):
                    graph_type = graph_item.get("@type", "")
                    if graph_type == "Recipe" or (
                        isinstance(graph_type, list) and "Recipe" in graph_type
                    ):
                        return graph_item

    return None


def _find_recipe_in_microdata(microdata_items: list) -> dict | None:
    """Find Recipe schema in microdata."""
    for item in microdata_items:
        if isinstance(item, dict):
            item_type = item.get("type", "")
            if "Recipe" in str(item_type):
                return item.get("properties", {})
    return None


def _extract_cuisine(recipe_data: dict) -> str | None:
    """Extract cuisine from recipe data."""
    cuisine = recipe_data.get("recipeCuisine")
    if isinstance(cuisine, list):
        return cuisine[0] if cuisine else None
    return cuisine
