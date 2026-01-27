"""Main recipe extraction orchestration."""

import logging
import re
from urllib.parse import urlparse

from .json_ld import extract_with_json_ld
from .models import ExtractionMethod, ExtractionResult
from .scrapers import extract_with_scraper

logger = logging.getLogger(__name__)

# Default fallback message when all extraction methods fail
DEFAULT_FALLBACK_MESSAGE = (
    "Copy the recipe text from the website and paste it in chat. "
    "Alfred can help you turn it into a saved recipe."
)


def extract_recipe(url: str) -> ExtractionResult:
    """
    Extract recipe from URL using the best available method.

    Extraction pipeline:
    1. Validate URL format
    2. Try recipe-scrapers library (400+ sites with custom parsers)
    3. Fall back to JSON-LD extraction (Schema.org markup)
    4. Return failure with chat fallback message

    Args:
        url: The URL of the recipe page to extract

    Returns:
        ExtractionResult with preview data on success, error details on failure
    """
    # Validate URL
    validation_error = _validate_url(url)
    if validation_error:
        return ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error=validation_error,
        )

    # Try recipe-scrapers first (best coverage for popular sites)
    logger.info(f"Attempting scraper extraction for {url}")
    result = extract_with_scraper(url)

    if result.success:
        logger.info(f"Scraper extraction succeeded for {url}")
        return result

    # If scraper failed due to network/access issues, don't retry with JSON-LD
    if result.error and any(
        msg in result.error.lower()
        for msg in ["timeout", "blocked", "login", "not found", "http"]
    ):
        result.fallback_message = result.fallback_message or DEFAULT_FALLBACK_MESSAGE
        return result

    # Try JSON-LD extraction as fallback
    logger.info(f"Scraper failed, trying JSON-LD extraction for {url}")
    json_ld_result = extract_with_json_ld(url)

    if json_ld_result.success:
        logger.info(f"JSON-LD extraction succeeded for {url}")
        return json_ld_result

    # Both methods failed
    logger.info(f"All extraction methods failed for {url}")
    return ExtractionResult(
        success=False,
        method=ExtractionMethod.FAILED,
        error="Could not extract recipe from this URL",
        fallback_message=DEFAULT_FALLBACK_MESSAGE,
    )


def _validate_url(url: str) -> str | None:
    """
    Validate URL format.

    Returns error message if invalid, None if valid.
    """
    if not url or not url.strip():
        return "URL is required"

    url = url.strip()

    # Basic URL pattern check
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return "URL must start with http:// or https://"

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return "Invalid URL format"
        if not parsed.scheme in ("http", "https"):
            return "URL must use http or https protocol"
    except Exception:
        return "Invalid URL format"

    return None
