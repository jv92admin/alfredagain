"""Normalization utilities for recipe data."""

import re


def parse_duration(duration: str | None) -> int | None:
    """
    Parse ISO 8601 duration to minutes.

    Examples:
        PT30M -> 30
        PT1H -> 60
        PT1H30M -> 90
        PT2H15M -> 135
    """
    if not duration:
        return None

    # Handle already-integer values
    if isinstance(duration, int):
        return duration

    # Match ISO 8601 duration pattern
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", str(duration))
    if not match:
        # Try parsing as plain number
        try:
            return int(duration)
        except (ValueError, TypeError):
            return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes if (hours or minutes) else None


def parse_servings(yield_str: str | None) -> int | None:
    """
    Parse recipe yield/servings to integer.

    Examples:
        "4 servings" -> 4
        "Serves 6" -> 6
        "4" -> 4
        "Makes 12 cookies" -> 12
    """
    if not yield_str:
        return None

    if isinstance(yield_str, int):
        return yield_str

    # Extract first number from string
    match = re.search(r"(\d+)", str(yield_str))
    if match:
        return int(match.group(1))

    return None


def extract_instructions_text(instructions: list | str | None) -> list[str]:
    """
    Extract instruction text from various formats.

    Handles:
        - Plain strings (split by newlines/numbers)
        - List of strings
        - List of HowToStep dicts with 'text' field
    """
    if not instructions:
        return []

    # Already a list
    if isinstance(instructions, list):
        result = []
        for item in instructions:
            if isinstance(item, str):
                # Clean up the string
                text = item.strip()
                if text:
                    result.append(text)
            elif isinstance(item, dict):
                # HowToStep format
                text = item.get("text") or item.get("@text") or ""
                if isinstance(text, str) and text.strip():
                    result.append(text.strip())
        return result

    # Single string - split by numbered steps or newlines
    if isinstance(instructions, str):
        # Try splitting by numbered patterns like "1." or "1)"
        steps = re.split(r"\n\s*\d+[\.\)]\s*", instructions)
        if len(steps) > 1:
            return [s.strip() for s in steps if s.strip()]

        # Fall back to splitting by double newlines
        steps = instructions.split("\n\n")
        if len(steps) > 1:
            return [s.strip() for s in steps if s.strip()]

        # Single paragraph - return as single instruction
        return [instructions.strip()] if instructions.strip() else []

    return []


def normalize_ingredients(ingredients: list | None) -> list[str]:
    """
    Normalize ingredients to list of strings.

    Handles:
        - List of strings
        - List of dicts with 'name' or 'text' field
    """
    if not ingredients:
        return []

    result = []
    for item in ingredients:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("name") or ""
            if isinstance(text, str) and text.strip():
                result.append(text.strip())

    return result


def extract_image_url(image: str | dict | list | None) -> str | None:
    """
    Extract image URL from various formats.

    Handles:
        - Plain URL string
        - Dict with 'url' field
        - List of images (take first)
    """
    if not image:
        return None

    if isinstance(image, str):
        return image if image.startswith("http") else None

    if isinstance(image, dict):
        url = image.get("url") or image.get("@url") or image.get("contentUrl")
        if isinstance(url, str) and url.startswith("http"):
            return url

    if isinstance(image, list) and len(image) > 0:
        return extract_image_url(image[0])

    return None
