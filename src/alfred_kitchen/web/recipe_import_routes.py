"""API endpoints for recipe import from external URLs."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from alfred_kitchen.db.client import get_authenticated_client
from alfred_kitchen.recipe_import import extract_recipe, ExtractionMethod, parse_and_link_ingredients
from alfred_kitchen.web.auth import AuthenticatedUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recipe-import"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ImportRequest(BaseModel):
    """Request to import a recipe from URL."""

    url: str


class ParsedIngredientResponse(BaseModel):
    """Parsed ingredient with structured fields."""

    name: str
    quantity: float | None = None
    unit: str | None = None
    notes: str | None = None
    is_optional: bool = False
    raw_text: str | None = None  # Original string for reference
    ingredient_id: str | None = None  # Link to master ingredients DB
    match_confidence: float = 0  # Confidence of ingredient_id match


class RecipePreviewResponse(BaseModel):
    """Extracted recipe preview for user review."""

    name: str
    source_url: str
    description: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    cuisine: str | None = None
    ingredients_raw: list[str] = []  # Keep for fallback
    ingredients_parsed: list[ParsedIngredientResponse] = []  # LLM-parsed structured data
    instructions: list[str] = []
    image_url: str | None = None


class ImportResponse(BaseModel):
    """Response from recipe import attempt."""

    success: bool
    method: str  # "scraper" | "json_ld" | "failed"
    preview: RecipePreviewResponse | None = None
    error: str | None = None
    fallback_message: str | None = None


class IngredientInput(BaseModel):
    """Ingredient data for saving."""

    name: str
    quantity: float | None = None
    unit: str | None = None
    notes: str | None = None
    is_optional: bool = False
    ingredient_id: str | None = None  # Link to master ingredients DB


class ConfirmRequest(BaseModel):
    """Request to save an imported recipe after user review/edit."""

    source_url: str
    name: str
    description: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    cuisine: str | None = None
    instructions: list[str] = []
    tags: list[str] = []
    ingredients: list[IngredientInput] = []


class ConfirmResponse(BaseModel):
    """Response after saving imported recipe."""

    success: bool
    recipe_id: str | None = None
    error: str | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/recipes/import", response_model=ImportResponse)
async def import_recipe(
    req: ImportRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ImportResponse:
    """
    Extract recipe data from a URL for preview.

    Extraction pipeline:
    1. Try recipe-scrapers library (400+ sites)
    2. Fall back to JSON-LD extraction
    3. Return failure with chat fallback message

    Returns extracted data for user review before saving.
    """
    logger.info(f"Import request from user {user.id} for URL: {req.url}")

    result = extract_recipe(req.url)

    if result.success and result.preview:
        # Parse raw ingredients with LLM and link to master ingredients DB
        ingredients_parsed = []
        if result.preview.ingredients_raw:
            try:
                parsed = await parse_and_link_ingredients(result.preview.ingredients_raw)
                ingredients_parsed = [
                    ParsedIngredientResponse(
                        name=p["name"],
                        quantity=p["quantity"],
                        unit=p["unit"],
                        notes=p["notes"],
                        is_optional=p["is_optional"],
                        raw_text=p.get("raw_text"),
                        ingredient_id=p.get("ingredient_id"),
                        match_confidence=p.get("match_confidence", 0),
                    )
                    for p in parsed
                ]
            except Exception as e:
                logger.warning(f"Ingredient parsing failed, using raw strings: {e}")
                # Fallback: use raw strings as names
                ingredients_parsed = [
                    ParsedIngredientResponse(name=raw, raw_text=raw)
                    for raw in result.preview.ingredients_raw
                ]

        preview = RecipePreviewResponse(
            name=result.preview.name,
            source_url=result.preview.source_url,
            description=result.preview.description,
            prep_time_minutes=result.preview.prep_time_minutes,
            cook_time_minutes=result.preview.cook_time_minutes,
            servings=result.preview.servings,
            cuisine=result.preview.cuisine,
            ingredients_raw=result.preview.ingredients_raw,
            ingredients_parsed=ingredients_parsed,
            instructions=result.preview.instructions,
            image_url=result.preview.image_url,
        )
        return ImportResponse(
            success=True,
            method=result.method.value,
            preview=preview,
        )

    return ImportResponse(
        success=False,
        method=result.method.value,
        error=result.error,
        fallback_message=result.fallback_message,
    )


@router.post("/recipes/import/confirm", response_model=ConfirmResponse)
async def confirm_import(
    req: ConfirmRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ConfirmResponse:
    """
    Save an imported recipe after user review/edit.

    The user may have edited fields from the preview before confirming.
    This uses the same creation logic as the standard recipe creation endpoint.
    """
    logger.info(f"Confirm import from user {user.id} for recipe: {req.name}")

    # Validate required fields
    if not req.name or not req.name.strip():
        return ConfirmResponse(
            success=False,
            error="Recipe name is required",
        )

    if not req.instructions:
        return ConfirmResponse(
            success=False,
            error="At least one instruction step is required",
        )

    try:
        client = get_authenticated_client(user.access_token)

        # Create recipe
        recipe_data = {
            "user_id": user.id,
            "name": req.name.strip(),
            "description": req.description,
            "prep_time_minutes": req.prep_time_minutes,
            "cook_time_minutes": req.cook_time_minutes,
            "servings": req.servings,
            "cuisine": req.cuisine,
            "instructions": req.instructions,
            "tags": req.tags,
            "source_url": req.source_url,
        }

        recipe_result = client.table("recipes").insert(recipe_data).execute()

        if not recipe_result.data:
            return ConfirmResponse(
                success=False,
                error="Failed to create recipe",
            )

        recipe = recipe_result.data[0]
        recipe_id = recipe["id"]

        # Create ingredients if provided
        if req.ingredients:
            ingredients_data = []
            for ing in req.ingredients:
                if not ing.name or not ing.name.strip():
                    continue  # Skip empty ingredients

                ingredients_data.append({
                    "recipe_id": recipe_id,
                    "user_id": user.id,
                    "name": ing.name.strip(),
                    "quantity": ing.quantity,
                    "unit": ing.unit,
                    "notes": ing.notes,
                    "is_optional": ing.is_optional,
                    "ingredient_id": ing.ingredient_id,
                })

            if ingredients_data:
                ing_result = client.table("recipe_ingredients").insert(ingredients_data).execute()
                if not ing_result.data:
                    logger.warning(f"Failed to create ingredients for recipe {recipe_id}")

        logger.info(f"Recipe imported successfully: {recipe_id}")
        return ConfirmResponse(
            success=True,
            recipe_id=str(recipe_id),
        )

    except Exception as e:
        logger.exception(f"Failed to save imported recipe: {e}")
        return ConfirmResponse(
            success=False,
            error=f"Failed to save recipe: {str(e)}",
        )
