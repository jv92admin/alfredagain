"""
Ingredient Preference Discovery for Onboarding.

Shows ingredients by category, user marks likes/dislikes.
Uses existing ingredients table with category field.
Stores preferences in flavor_preferences table.
"""

import logging
import random
from typing import Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Categories to show for preference discovery
# These are the most meaningful for taste preferences
# NOTE: db_categories must match actual values in ingredients.category column
DISCOVERY_CATEGORIES = [
    {
        "id": "proteins",
        "label": "Proteins",
        "db_categories": ["poultry", "beef", "pork", "fish", "shellfish", "lamb"],
        "description": "Meats, fish, and protein sources",
    },
    {
        "id": "vegetables", 
        "label": "Vegetables",
        "db_categories": ["vegetables", "produce"],
        "description": "Fresh vegetables",
    },
    {
        "id": "fruits",
        "label": "Fruits",
        "db_categories": ["fruits"],
        "description": "Fresh fruits",
    },
    {
        "id": "spices_herbs",
        "label": "Spices & Herbs",
        "db_categories": ["spices", "spice", "herbs"],
        "description": "Seasonings and fresh herbs",
    },
    {
        "id": "cheese_dairy",
        "label": "Cheese & Dairy",
        "db_categories": ["cheese", "dairy"],
        "description": "Cheeses and dairy products",
    },
]

# Categories to SKIP (too basic to be preference signals)
SKIP_CATEGORIES = {
    "bread", "pasta", "rice", "noodles_asian",
    "oils", "vinegar", "pantry_staples", "baking",
    "eggs", "dairy_milk",  # Most people use these
    "condiments", "sauces_prepared",
}

# Minimum preferences before suggesting "continue"
MIN_PREFERENCES_THRESHOLD = 20


@dataclass
class IngredientPreference:
    """A single ingredient preference."""
    ingredient_id: str
    ingredient_name: str
    category: str
    preference: Literal["like", "dislike"]


def get_discovery_categories() -> list[dict]:
    """Get categories available for discovery."""
    return DISCOVERY_CATEGORIES


async def get_ingredients_for_category(
    category_id: str,
    limit: int = 8,
    exclude_ids: list[str] | None = None,
    seed_from_likes: list[str] | None = None,
) -> list[dict]:
    """
    Get ingredients for a discovery category.
    
    If seed_from_likes is provided, uses embeddings to find similar ingredients.
    Otherwise falls back to random selection.
    
    Args:
        category_id: One of the DISCOVERY_CATEGORIES ids
        limit: Max ingredients to return
        exclude_ids: Ingredient IDs to exclude (already shown)
        seed_from_likes: List of ingredient IDs user likes (for embedding similarity)
    
    Returns:
        List of {id, name, category}
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    # Find the category config
    category_config = next(
        (c for c in DISCOVERY_CATEGORIES if c["id"] == category_id),
        None
    )
    
    if not category_config:
        logger.warning(f"Unknown category: {category_id}")
        return []
    
    db_categories = category_config["db_categories"]
    exclude_ids = exclude_ids or []
    
    # Try embedding-based search if we have seed likes
    if seed_from_likes:
        similar = await _get_similar_ingredients_by_embedding(
            seed_ids=seed_from_likes,
            db_categories=db_categories,
            exclude_ids=exclude_ids,
            limit=limit,
        )
        if similar:
            return similar
    
    # Fallback: random selection from category
    try:
        query = client.table("ingredients").select(
            "id, name, category"
        ).in_("category", db_categories)
        
        if exclude_ids:
            query = query.not_.in_("id", exclude_ids)
        
        result = query.limit(100).execute()
        
        if result.data:
            ingredients = result.data
            random.shuffle(ingredients)
            
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "category": row.get("category"),
                }
                for row in ingredients[:limit]
            ]
        else:
            logger.warning(f"No ingredients found for category {category_id}")
    
    except Exception as e:
        logger.error(f"Failed to get ingredients for {category_id}: {e}")
    
    return []


async def _get_similar_ingredients_by_embedding(
    seed_ids: list[str],
    db_categories: list[str],
    exclude_ids: list[str],
    limit: int = 8,
) -> list[dict]:
    """
    Find ingredients similar to seed ingredients using embeddings.
    
    Args:
        seed_ids: Ingredient IDs to find similar to
        db_categories: Filter to these categories
        exclude_ids: IDs to exclude from results
        limit: Max results
    
    Returns:
        List of similar ingredients, or empty if embeddings not available
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    try:
        # Get embeddings for seed ingredients
        seed_result = client.table("ingredients").select(
            "embedding"
        ).in_("id", seed_ids).not_.is_("embedding", "null").execute()
        
        if not seed_result.data:
            return []
        
        # Average the seed embeddings
        embeddings = [r["embedding"] for r in seed_result.data if r.get("embedding")]
        if not embeddings:
            return []
        
        # Simple average of embeddings
        avg_embedding = [
            sum(e[i] for e in embeddings) / len(embeddings)
            for i in range(len(embeddings[0]))
        ]
        
        # Find similar using vector search
        # Use the match_ingredients RPC if available, otherwise raw query
        result = client.rpc(
            "match_ingredients_by_embedding",
            {
                "query_embedding": avg_embedding,
                "match_threshold": 0.5,
                "match_count": limit * 3,  # Fetch more to filter
            }
        ).execute()
        
        if result.data:
            # Filter to requested categories and exclude IDs
            filtered = [
                r for r in result.data
                if r.get("category") in db_categories
                and r.get("id") not in exclude_ids
                and r.get("id") not in seed_ids
            ]
            
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "category": row.get("category"),
                }
                for row in filtered[:limit]
            ]
    
    except Exception as e:
        # Embedding search not available, that's OK
        logger.debug(f"Embedding search failed (falling back to random): {e}")
    
    return []


async def get_next_discovery_batch(
    shown_ids: list[str],
    preferences_count: int,
) -> dict:
    """
    Get next batch of ingredients for discovery.
    
    Rotates through categories to show variety.
    
    Args:
        shown_ids: Ingredient IDs already shown
        preferences_count: How many preferences user has marked
    
    Returns:
        {
            "ingredients": [...],
            "category": {...},
            "can_continue": bool,  # True if 20+ preferences
            "total_preferences": int,
        }
    """
    # Rotate through categories based on how many shown
    category_index = (len(shown_ids) // 8) % len(DISCOVERY_CATEGORIES)
    category = DISCOVERY_CATEGORIES[category_index]
    
    ingredients = await get_ingredients_for_category(
        category["id"],
        limit=8,
        exclude_ids=shown_ids,
    )
    
    return {
        "ingredients": ingredients,
        "category": category,
        "can_continue": preferences_count >= MIN_PREFERENCES_THRESHOLD,
        "total_preferences": preferences_count,
        "message": (
            f"You've marked {preferences_count} preferences. "
            + ("Feel free to continue or move on!" if preferences_count >= MIN_PREFERENCES_THRESHOLD 
               else f"Mark {MIN_PREFERENCES_THRESHOLD - preferences_count} more to continue.")
        ),
    }


async def save_ingredient_preference(
    user_id: str,
    ingredient_id: str,
    preference: Literal["like", "dislike"],
) -> bool:
    """
    Save an ingredient preference to flavor_preferences table.
    
    Args:
        user_id: User's ID
        ingredient_id: Ingredient's ID
        preference: "like" (+1) or "dislike" (-1)
    
    Returns:
        True if saved successfully
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    preference_score = 1.0 if preference == "like" else -1.0
    
    try:
        # Upsert to flavor_preferences (on conflict of user_id + ingredient_id)
        client.table("flavor_preferences").upsert(
            {
                "user_id": user_id,
                "ingredient_id": ingredient_id,
                "preference_score": preference_score,
            },
            on_conflict="user_id,ingredient_id"
        ).execute()
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to save preference: {e}")
        return False


async def save_ingredient_preferences_batch(
    user_id: str,
    preferences: list[dict],
) -> int:
    """
    Save multiple ingredient preferences at once.
    
    Args:
        user_id: User's ID
        preferences: List of {ingredient_id, preference: "like"|"dislike"}
    
    Returns:
        Number of preferences saved
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    records = []
    for pref in preferences:
        if pref.get("ingredient_id") and pref.get("preference"):
            score = 1.0 if pref["preference"] == "like" else -1.0
            records.append({
                "user_id": user_id,
                "ingredient_id": pref["ingredient_id"],
                "preference_score": score,
            })
    
    if not records:
        return 0
    
    try:
        client.table("flavor_preferences").upsert(
            records,
            on_conflict="user_id,ingredient_id"
        ).execute()
        return len(records)
    except Exception as e:
        logger.error(f"Failed to save preferences batch: {e}")
        return 0


async def get_user_preferences_count(user_id: str) -> int:
    """Get count of user's ingredient preferences."""
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    try:
        result = client.table("flavor_preferences").select(
            "id", count="exact"
        ).eq("user_id", user_id).execute()
        
        return result.count or 0
    except Exception as e:
        logger.error(f"Failed to get preferences count: {e}")
        return 0


async def get_user_preferences_summary(user_id: str) -> dict:
    """
    Get summary of user's ingredient preferences.
    
    Returns:
        {
            "total": int,
            "likes": int,
            "dislikes": int,
            "top_likes": [...],
            "top_dislikes": [...],
        }
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    try:
        # Get all preferences with ingredient names
        result = client.table("flavor_preferences").select(
            "ingredient_id, preference_score, ingredients(name, category)"
        ).eq("user_id", user_id).execute()
        
        if not result.data:
            return {"total": 0, "likes": 0, "dislikes": 0, "top_likes": [], "top_dislikes": []}
        
        likes = [r for r in result.data if r["preference_score"] > 0]
        dislikes = [r for r in result.data if r["preference_score"] < 0]
        
        return {
            "total": len(result.data),
            "likes": len(likes),
            "dislikes": len(dislikes),
            "top_likes": [
                {"name": r["ingredients"]["name"], "category": r["ingredients"].get("category")}
                for r in likes[:10] if r.get("ingredients")
            ],
            "top_dislikes": [
                {"name": r["ingredients"]["name"], "category": r["ingredients"].get("category")}
                for r in dislikes[:10] if r.get("ingredients")
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get preferences summary: {e}")
        return {"total": 0, "likes": 0, "dislikes": 0, "top_likes": [], "top_dislikes": []}
