"""Tests for recipe import module."""

import pytest

from alfred_kitchen.recipe_import.normalizer import (
    parse_duration,
    parse_servings,
    extract_instructions_text,
    normalize_ingredients,
    extract_image_url,
)
from alfred_kitchen.recipe_import.models import (
    ExtractionMethod,
    ExtractionResult,
    RecipePreview,
)
from alfred_kitchen.recipe_import.extractor import _validate_url


class TestParseDuration:
    """Tests for ISO 8601 duration parsing."""

    def test_parse_minutes_only(self):
        assert parse_duration("PT30M") == 30
        assert parse_duration("PT5M") == 5
        assert parse_duration("PT45M") == 45

    def test_parse_hours_only(self):
        assert parse_duration("PT1H") == 60
        assert parse_duration("PT2H") == 120

    def test_parse_hours_and_minutes(self):
        assert parse_duration("PT1H30M") == 90
        assert parse_duration("PT2H15M") == 135
        assert parse_duration("PT1H45M") == 105

    def test_parse_plain_number(self):
        assert parse_duration("30") == 30
        assert parse_duration(45) == 45

    def test_parse_none_or_empty(self):
        assert parse_duration(None) is None
        assert parse_duration("") is None

    def test_parse_invalid_format(self):
        assert parse_duration("invalid") is None
        assert parse_duration("30 minutes") is None


class TestParseServings:
    """Tests for recipe yield/servings parsing."""

    def test_parse_plain_number(self):
        assert parse_servings("4") == 4
        assert parse_servings(6) == 6

    def test_parse_with_servings_text(self):
        assert parse_servings("4 servings") == 4
        assert parse_servings("6 Servings") == 6
        assert parse_servings("Serves 8") == 8

    def test_parse_with_makes_text(self):
        assert parse_servings("Makes 12 cookies") == 12
        assert parse_servings("Makes about 24") == 24

    def test_parse_none_or_empty(self):
        assert parse_servings(None) is None
        assert parse_servings("") is None


class TestExtractInstructionsText:
    """Tests for instruction text extraction."""

    def test_extract_from_string_list(self):
        instructions = ["Step 1", "Step 2", "Step 3"]
        result = extract_instructions_text(instructions)
        assert result == ["Step 1", "Step 2", "Step 3"]

    def test_extract_from_howto_step_dicts(self):
        instructions = [
            {"@type": "HowToStep", "text": "Mix ingredients"},
            {"@type": "HowToStep", "text": "Bake for 30 minutes"},
        ]
        result = extract_instructions_text(instructions)
        assert result == ["Mix ingredients", "Bake for 30 minutes"]

    def test_extract_from_numbered_string(self):
        instructions = "1. Mix ingredients\n2. Bake for 30 minutes\n3. Serve"
        result = extract_instructions_text(instructions)
        assert "Mix ingredients" in result[0] or len(result) >= 2

    def test_extract_empty_or_none(self):
        assert extract_instructions_text(None) == []
        assert extract_instructions_text([]) == []

    def test_filter_empty_strings(self):
        instructions = ["Step 1", "", "  ", "Step 2"]
        result = extract_instructions_text(instructions)
        assert result == ["Step 1", "Step 2"]


class TestNormalizeIngredients:
    """Tests for ingredient normalization."""

    def test_normalize_string_list(self):
        ingredients = ["2 cups flour", "1 tsp salt"]
        result = normalize_ingredients(ingredients)
        assert result == ["2 cups flour", "1 tsp salt"]

    def test_normalize_dict_list(self):
        ingredients = [
            {"text": "2 cups flour"},
            {"name": "1 tsp salt"},
        ]
        result = normalize_ingredients(ingredients)
        assert result == ["2 cups flour", "1 tsp salt"]

    def test_filter_empty_strings(self):
        ingredients = ["2 cups flour", "", "  ", "1 tsp salt"]
        result = normalize_ingredients(ingredients)
        assert result == ["2 cups flour", "1 tsp salt"]

    def test_empty_or_none(self):
        assert normalize_ingredients(None) == []
        assert normalize_ingredients([]) == []


class TestExtractImageUrl:
    """Tests for image URL extraction."""

    def test_extract_from_string(self):
        assert extract_image_url("https://example.com/image.jpg") == "https://example.com/image.jpg"

    def test_extract_from_dict(self):
        image = {"url": "https://example.com/image.jpg"}
        assert extract_image_url(image) == "https://example.com/image.jpg"

    def test_extract_from_dict_content_url(self):
        image = {"contentUrl": "https://example.com/image.jpg"}
        assert extract_image_url(image) == "https://example.com/image.jpg"

    def test_extract_from_list(self):
        images = ["https://example.com/image1.jpg", "https://example.com/image2.jpg"]
        assert extract_image_url(images) == "https://example.com/image1.jpg"

    def test_reject_non_http_url(self):
        assert extract_image_url("not-a-url") is None
        assert extract_image_url("/relative/path.jpg") is None

    def test_none_or_empty(self):
        assert extract_image_url(None) is None
        assert extract_image_url({}) is None


class TestValidateUrl:
    """Tests for URL validation."""

    def test_valid_https_url(self):
        assert _validate_url("https://example.com/recipe") is None

    def test_valid_http_url(self):
        assert _validate_url("http://example.com/recipe") is None

    def test_missing_protocol(self):
        error = _validate_url("example.com/recipe")
        assert error is not None
        assert "http" in error.lower()

    def test_empty_url(self):
        error = _validate_url("")
        assert error is not None

    def test_none_url(self):
        error = _validate_url(None)
        assert error is not None

    def test_whitespace_only(self):
        error = _validate_url("   ")
        assert error is not None


class TestModels:
    """Tests for data models."""

    def test_extraction_method_enum(self):
        assert ExtractionMethod.SCRAPER.value == "scraper"
        assert ExtractionMethod.JSON_LD.value == "json_ld"
        assert ExtractionMethod.FAILED.value == "failed"

    def test_recipe_preview_defaults(self):
        preview = RecipePreview(name="Test Recipe", source_url="https://example.com")
        assert preview.name == "Test Recipe"
        assert preview.source_url == "https://example.com"
        assert preview.description is None
        assert preview.ingredients_raw == []
        assert preview.instructions == []

    def test_extraction_result_success(self):
        preview = RecipePreview(name="Test", source_url="https://example.com")
        result = ExtractionResult(
            success=True,
            method=ExtractionMethod.SCRAPER,
            preview=preview,
        )
        assert result.success is True
        assert result.method == ExtractionMethod.SCRAPER
        assert result.preview is not None
        assert result.error is None

    def test_extraction_result_failure(self):
        result = ExtractionResult(
            success=False,
            method=ExtractionMethod.FAILED,
            error="Could not extract recipe",
            fallback_message="Try pasting in chat",
        )
        assert result.success is False
        assert result.error == "Could not extract recipe"
        assert result.fallback_message is not None
