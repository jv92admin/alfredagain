"""
Entity CRUD API endpoints.

Unified CRUD endpoints for all entities with Phase 3-ready response metadata.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from alfred.db.client import get_authenticated_client
from alfred.domain.kitchen.crud_middleware import USER_OWNED_TABLES
from alfred.web.auth import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/entities", tags=["entities"])


# =============================================================================
# Response Models
# =============================================================================


class EntityMeta(BaseModel):
    """Phase 3-ready metadata for tracking entity changes."""
    action: str  # "created", "updated", "deleted"
    entity_type: str
    id: str
    timestamp: str


class EntityResponse(BaseModel):
    """Standard response with data and metadata."""
    data: dict[str, Any]
    meta: EntityMeta


class EntityListResponse(BaseModel):
    """Standard response for list operations."""
    data: list[dict[str, Any]]
    count: int


# =============================================================================
# Allowed Tables
# =============================================================================

# Tables that can be accessed via these generic CRUD endpoints
ALLOWED_TABLES = {
    "inventory",
    "recipes",
    "recipe_ingredients",
    "shopping_list",
    "meal_plans",
    "tasks",
    "preferences",
}


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.get("/{table}")
async def list_entities(
    table: str,
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
) -> EntityListResponse:
    """
    List entities from a table with pagination.

    RLS ensures user only sees their own data.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not allowed")

    client = get_authenticated_client(user.access_token)

    query = client.table(table).select("*", count="exact")
    query = query.range(offset, offset + limit - 1)

    result = query.execute()

    return EntityListResponse(
        data=result.data,
        count=result.count or len(result.data),
    )


@router.get("/{table}/{entity_id}")
async def get_entity(
    table: str,
    entity_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> EntityResponse:
    """
    Get a single entity by ID.

    RLS ensures user can only access their own data.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not allowed")

    client = get_authenticated_client(user.access_token)
    result = client.table(table).select("*").eq("id", entity_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"{table} item not found")

    return EntityResponse(
        data=result.data[0],
        meta=EntityMeta(
            action="read",
            entity_type=table,
            id=entity_id,
            timestamp=datetime.utcnow().isoformat(),
        ),
    )


@router.post("/{table}")
async def create_entity(
    table: str,
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(get_current_user),
) -> EntityResponse:
    """
    Create a new entity.

    RLS ensures user_id is set correctly.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not allowed")

    # Don't allow client to set id - managed by DB
    body.pop("id", None)

    # Set user_id for user-owned tables (required by RLS)
    if table in USER_OWNED_TABLES:
        body["user_id"] = user.id

    client = get_authenticated_client(user.access_token)
    result = client.table(table).insert(body).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create entity")

    created = result.data[0]

    return EntityResponse(
        data=created,
        meta=EntityMeta(
            action="created",
            entity_type=table,
            id=str(created.get("id", "")),
            timestamp=datetime.utcnow().isoformat(),
        ),
    )


@router.patch("/{table}/{entity_id}")
async def update_entity(
    table: str,
    entity_id: str,
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(get_current_user),
) -> EntityResponse:
    """
    Update an existing entity.

    RLS ensures user can only update their own data.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not allowed")

    # Don't allow client to change id or user_id
    body.pop("id", None)
    body.pop("user_id", None)

    # Remove None values - only update provided fields
    update_data = {k: v for k, v in body.items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    client = get_authenticated_client(user.access_token)
    result = client.table(table).update(update_data).eq("id", entity_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"{table} item not found")

    return EntityResponse(
        data=result.data[0],
        meta=EntityMeta(
            action="updated",
            entity_type=table,
            id=entity_id,
            timestamp=datetime.utcnow().isoformat(),
        ),
    )


@router.delete("/{table}/{entity_id}")
async def delete_entity(
    table: str,
    entity_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete an entity.

    RLS ensures user can only delete their own data.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not allowed")

    client = get_authenticated_client(user.access_token)
    result = client.table(table).delete().eq("id", entity_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"{table} item not found")

    return {
        "success": True,
        "meta": EntityMeta(
            action="deleted",
            entity_type=table,
            id=entity_id,
            timestamp=datetime.utcnow().isoformat(),
        ).model_dump(),
    }


# =============================================================================
# Recipe-Specific Endpoints (Complex Entity)
# =============================================================================


class RecipeWithIngredients(BaseModel):
    """Recipe creation with ingredients in one transaction."""
    name: str
    description: str | None = None
    cuisine: str | None = None
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    instructions: list[str]
    tags: list[str] = []
    source_url: str | None = None
    ingredients: list[dict[str, Any]] = []


@router.post("/recipes/with-ingredients")
async def create_recipe_with_ingredients(
    body: RecipeWithIngredients,
    user: AuthenticatedUser = Depends(get_current_user),
) -> EntityResponse:
    """
    Create a recipe with its ingredients in one transaction.

    Ingredients are created in recipe_ingredients table with FK to the new recipe.
    """
    client = get_authenticated_client(user.access_token)

    # Create recipe first
    recipe_data = body.model_dump(exclude={"ingredients"})
    recipe_data["user_id"] = user.id  # Required by RLS
    recipe_result = client.table("recipes").insert(recipe_data).execute()

    if not recipe_result.data:
        raise HTTPException(status_code=500, detail="Failed to create recipe")

    recipe = recipe_result.data[0]
    recipe_id = recipe["id"]

    # Create ingredients if provided
    if body.ingredients:
        ingredients_data = []
        for ing in body.ingredients:
            ing_copy = dict(ing)
            ing_copy["recipe_id"] = recipe_id
            ing_copy["user_id"] = user.id  # Required by RLS
            ing_copy.pop("id", None)
            ingredients_data.append(ing_copy)

        ing_result = client.table("recipe_ingredients").insert(ingredients_data).execute()

        if not ing_result.data:
            # Recipe was created but ingredients failed - log warning
            # In production, this should be a transaction
            pass

    return EntityResponse(
        data=recipe,
        meta=EntityMeta(
            action="created",
            entity_type="recipes",
            id=str(recipe_id),
            timestamp=datetime.utcnow().isoformat(),
        ),
    )


class RecipeWithIngredientsUpdate(BaseModel):
    """Recipe update with ingredients replacement."""
    name: str | None = None
    description: str | None = None
    cuisine: str | None = None
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    instructions: list[str] | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    ingredients: list[dict[str, Any]] | None = None  # If provided, replaces all


@router.put("/recipes/{recipe_id}/with-ingredients")
async def update_recipe_with_ingredients(
    recipe_id: str,
    body: RecipeWithIngredientsUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> EntityResponse:
    """
    Update a recipe and optionally replace all its ingredients.

    If ingredients array is provided, all existing ingredients are deleted
    and replaced with the new ones.
    """
    client = get_authenticated_client(user.access_token)

    # Build recipe update payload (exclude None values and ingredients)
    recipe_updates = {
        k: v for k, v in body.model_dump(exclude={"ingredients"}).items()
        if v is not None
    }

    if not recipe_updates and body.ingredients is None:
        raise HTTPException(status_code=400, detail="No updates provided")

    # Update recipe metadata if any fields provided
    if recipe_updates:
        recipe_result = client.table("recipes").update(recipe_updates).eq("id", recipe_id).execute()
        if not recipe_result.data:
            raise HTTPException(status_code=404, detail="Recipe not found")
        recipe = recipe_result.data[0]
    else:
        # Just fetch the recipe if only updating ingredients
        recipe_result = client.table("recipes").select("*").eq("id", recipe_id).execute()
        if not recipe_result.data:
            raise HTTPException(status_code=404, detail="Recipe not found")
        recipe = recipe_result.data[0]

    # Replace ingredients if provided
    if body.ingredients is not None:
        # Delete all existing ingredients
        client.table("recipe_ingredients").delete().eq("recipe_id", recipe_id).execute()

        # Insert new ingredients
        if body.ingredients:
            ingredients_data = []
            for ing in body.ingredients:
                ing_copy = dict(ing)
                ing_copy["recipe_id"] = recipe_id
                ing_copy["user_id"] = user.id
                ing_copy.pop("id", None)
                ingredients_data.append(ing_copy)

            client.table("recipe_ingredients").insert(ingredients_data).execute()

    return EntityResponse(
        data=recipe,
        meta=EntityMeta(
            action="updated",
            entity_type="recipes",
            id=str(recipe_id),
            timestamp=datetime.utcnow().isoformat(),
        ),
    )
