"""Data models for recipe import."""

from dataclasses import dataclass, field
from enum import Enum


class ExtractionMethod(str, Enum):
    """Method used to extract recipe data."""

    SCRAPER = "scraper"
    JSON_LD = "json_ld"
    FAILED = "failed"


@dataclass
class RecipePreview:
    """Extracted recipe ready for user review."""

    name: str
    source_url: str
    description: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    cuisine: str | None = None
    ingredients_raw: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    image_url: str | None = None


@dataclass
class ExtractionResult:
    """Result of recipe extraction attempt."""

    success: bool
    method: ExtractionMethod
    preview: RecipePreview | None = None
    error: str | None = None
    fallback_message: str | None = None
