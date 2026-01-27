"""Wrapper for recipe-scrapers library."""

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


def extract_with_scraper(url: str) -> ExtractionResult:
    """
    Extract recipe using recipe-scrapers library.

    This library has custom parsers for 400+ recipe sites.
    """
    try:
        from recipe_scrapers import scrape_html
        import httpx
    except ImportError as e:
        logger.warning(f"recipe-scrapers not installed: {e}")
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error="Recipe scraper library not available",
        )

    try:
        # Fetch the page with browser-like headers
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)

        # Check for login/paywall indicators
        if _is_login_page(html):
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.FAILED,
                error="This recipe requires login to view",
                fallback_message=(
                    "This recipe is behind a login wall. "
                    "Copy the recipe text and paste it in chat."
                ),
            )

        # Use recipe-scrapers to parse
        scraper = scrape_html(html, org_url=final_url)

        # Extract all available fields
        name = scraper.title()
        if not name:
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.FAILED,
                error="Could not find recipe name on this page",
            )

        ingredients = normalize_ingredients(scraper.ingredients())
        instructions = extract_instructions_text(scraper.instructions_list())

        preview = RecipePreview(
            name=name,
            source_url=final_url,
            description=_safe_call(scraper.description),
            prep_time_minutes=parse_duration(_safe_call(scraper.prep_time)),
            cook_time_minutes=parse_duration(_safe_call(scraper.cook_time)),
            servings=parse_servings(_safe_call(scraper.yields)),
            cuisine=_safe_call(scraper.cuisine),
            ingredients_raw=ingredients,
            instructions=instructions,
            image_url=extract_image_url(_safe_call(scraper.image)),
        )

        return ExtractionResult(
            success=True,
            method=ExtractionMethod.SCRAPER,
            preview=preview,
        )

    except httpx.TimeoutException:
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error="Request timed out. Please try again.",
            fallback_message="The website took too long to respond. Try again or paste the recipe text in chat.",
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.FAILED,
                error="This website blocked our request",
                fallback_message="This site blocks automated access. Copy the recipe text and paste it in chat.",
            )
        if e.response.status_code == 404:
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.FAILED,
                error="Recipe page not found",
            )
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error=f"Failed to fetch page: HTTP {e.response.status_code}",
        )
    except Exception as e:
        # recipe-scrapers throws various exceptions for unsupported sites
        logger.debug(f"Scraper failed for {url}: {e}")
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error=str(e),
        )


def _safe_call(func):
    """Safely call a scraper method, returning None on error."""
    try:
        return func()
    except Exception:
        return None


def _is_login_page(html: str) -> bool:
    """Detect if the page is a login/paywall page."""
    login_indicators = [
        "sign in to continue",
        "log in to view",
        "subscribe to read",
        "subscription required",
        "create an account",
        "please log in",
        "members only",
    ]
    html_lower = html.lower()
    return any(indicator in html_lower for indicator in login_indicators)
