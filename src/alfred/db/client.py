"""
Alfred V2 - Supabase Client.

Low-level database access. All queries go through here.
"""

from supabase import Client, create_client

from alfred.config import settings

# Singleton client instance
_client: Client | None = None


def get_client() -> Client:
    """
    Get the Supabase client.

    Uses singleton pattern to reuse connection.
    """
    global _client

    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key,
        )

    return _client


# =============================================================================
# Inventory Operations
# =============================================================================


async def get_inventory(user_id: str) -> list[dict]:
    """Get all inventory items for a user."""
    client = get_client()
    response = client.table("inventory").select("*").eq("user_id", user_id).execute()
    return response.data


async def get_inventory_item(item_id: str) -> dict | None:
    """Get a single inventory item by ID."""
    client = get_client()
    response = client.table("inventory").select("*").eq("id", item_id).single().execute()
    return response.data


async def add_inventory_item(user_id: str, item: dict) -> dict:
    """Add an item to inventory."""
    client = get_client()
    data = {"user_id": user_id, **item}
    response = client.table("inventory").insert(data).execute()
    return response.data[0]


async def update_inventory_item(user_id: str, item_id: str, updates: dict) -> dict:
    """Update an inventory item."""
    client = get_client()
    response = (
        client.table("inventory")
        .update(updates)
        .eq("id", item_id)
        .eq("user_id", user_id)  # Security: ensure user owns item
        .execute()
    )
    return response.data[0]


async def remove_inventory_item(user_id: str, item_id: str) -> dict:
    """
    Remove an inventory item.
    
    Returns the deleted item data for confirmation.
    """
    client = get_client()
    # First get the item to return its data
    item_resp = client.table("inventory").select("*").eq("id", item_id).eq("user_id", user_id).single().execute()
    item = item_resp.data
    
    # Then delete
    client.table("inventory").delete().eq("id", item_id).eq("user_id", user_id).execute()
    
    return item


# =============================================================================
# Ingredient Operations
# =============================================================================


async def get_ingredients(search: str | None = None, limit: int = 20) -> list[dict]:
    """Get ingredients, optionally filtered by search term."""
    client = get_client()
    query = client.table("ingredients").select("*")

    if search:
        # Simple ILIKE search on name
        query = query.ilike("name", f"%{search}%")

    response = query.limit(limit).execute()
    return response.data


async def get_ingredient_by_name(name: str) -> dict | None:
    """Get an ingredient by exact name."""
    client = get_client()
    response = client.table("ingredients").select("*").eq("name", name.lower()).maybe_single().execute()
    return response.data


async def upsert_ingredient(ingredient: dict) -> dict:
    """Create or update an ingredient."""
    client = get_client()
    response = client.table("ingredients").upsert(ingredient).execute()
    return response.data[0]


# =============================================================================
# Recipe Operations
# =============================================================================


async def get_recipes(user_id: str | None = None, limit: int = 20) -> list[dict]:
    """Get recipes, optionally filtered by user."""
    client = get_client()
    query = client.table("recipes").select("*")

    if user_id:
        # Get user's recipes and system recipes
        query = query.or_(f"user_id.eq.{user_id},is_system.eq.true")

    response = query.limit(limit).execute()
    return response.data


async def get_recipe(recipe_id: str) -> dict | None:
    """Get a recipe with its ingredients."""
    client = get_client()

    # Get recipe
    recipe_resp = client.table("recipes").select("*").eq("id", recipe_id).single().execute()
    if not recipe_resp.data:
        return None

    # Get ingredients
    ingredients_resp = client.table("recipe_ingredients").select("*").eq("recipe_id", recipe_id).execute()

    recipe = recipe_resp.data
    recipe["ingredients"] = ingredients_resp.data
    return recipe


async def create_recipe(user_id: str, recipe: dict) -> dict:
    """Create a new recipe with ingredients."""
    client = get_client()

    # Extract ingredients
    ingredients = recipe.pop("ingredients", [])

    # Create recipe
    recipe_data = {"user_id": user_id, **recipe}
    recipe_resp = client.table("recipes").insert(recipe_data).execute()
    created_recipe = recipe_resp.data[0]

    # Create recipe ingredients
    if ingredients:
        ingredient_data = [{"recipe_id": created_recipe["id"], **ing} for ing in ingredients]
        client.table("recipe_ingredients").insert(ingredient_data).execute()

    return created_recipe


# =============================================================================
# Preferences Operations
# =============================================================================


async def get_preferences(user_id: str) -> dict | None:
    """Get user preferences."""
    client = get_client()
    response = client.table("preferences").select("*").eq("user_id", user_id).maybe_single().execute()
    return response.data


async def upsert_preferences(user_id: str, preferences: dict) -> dict:
    """Create or update user preferences."""
    client = get_client()
    data = {"user_id": user_id, **preferences}
    response = client.table("preferences").upsert(data).execute()
    return response.data[0]


# =============================================================================
# Meal Plan Operations
# =============================================================================


async def get_meal_plans(user_id: str, start_date: str, end_date: str) -> list[dict]:
    """Get meal plans for a date range."""
    client = get_client()
    response = (
        client.table("meal_plans")
        .select("*, recipes(*)")
        .eq("user_id", user_id)
        .gte("date", start_date)
        .lte("date", end_date)
        .order("date")
        .execute()
    )
    return response.data


async def create_meal_plan(user_id: str, meal_plan: dict) -> dict:
    """Create a meal plan entry."""
    client = get_client()
    data = {"user_id": user_id, **meal_plan}
    response = client.table("meal_plans").insert(data).execute()
    return response.data[0]


# =============================================================================
# Shopping List Operations
# =============================================================================


async def get_shopping_list(user_id: str) -> list[dict]:
    """Get user's shopping list."""
    client = get_client()
    response = (
        client.table("shopping_list").select("*").eq("user_id", user_id).eq("is_purchased", False).execute()
    )
    return response.data


async def add_to_shopping_list(user_id: str, item: dict) -> dict:
    """Add item to shopping list."""
    client = get_client()
    data = {"user_id": user_id, **item}
    response = client.table("shopping_list").insert(data).execute()
    return response.data[0]


async def mark_purchased(item_id: str) -> dict:
    """Mark a shopping list item as purchased."""
    client = get_client()
    response = client.table("shopping_list").update({"is_purchased": True}).eq("id", item_id).execute()
    return response.data[0]

