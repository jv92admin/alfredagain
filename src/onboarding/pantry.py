"""
Pantry Seeding for Onboarding.

Provides ingredient search for users to add what they have in their pantry.
Uses existing ingredient_lookup infrastructure.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def search_ingredients(
    query: str, 
    limit: int = 10,
    user_id: Optional[str] = None,
) -> list[dict]:
    """
    Search ingredients database for pantry seeding.
    
    Uses smart lookup from ingredient_lookup.py which:
    - Scores by word match count + similarity
    - Prefers shorter/canonical names ("eggs" over "century eggs")
    
    Args:
        query: Search term
        limit: Max results to return
        user_id: Optional user ID (for authenticated queries)
    
    Returns:
        List of ingredient dicts: {id, name, category}
    """
    from alfred.tools.ingredient_lookup import lookup_ingredient
    
    if not query or len(query.strip()) < 2:
        return []
    
    try:
        # Use smart multi-match lookup (scores by word match + prefers shorter names)
        matches = await lookup_ingredient(
            query.strip(),
            operation="read",
            use_semantic=False,  # Skip slow embedding lookup for search
            limit=limit,
        )
        
        if matches:
            # lookup_ingredient returns list when limit > 1
            return [
                {
                    "id": m.id,
                    "name": m.name,
                    "category": m.category,
                }
                for m in matches
            ]
    except Exception as e:
        logger.warning(f"Smart search failed, falling back to ilike: {e}")
        
        # Fallback to simple ilike search
        from alfred.db.client import get_service_client
        client = get_service_client()
        
        result = client.table("ingredients").select(
            "id, name, category"
        ).ilike("name", f"%{query}%").order("name").limit(limit).execute()
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "category": row.get("category"),
            }
            for row in result.data
        ]
    
    return []


async def get_common_staples() -> list[dict]:
    """
    Get common pantry staples for quick-add.
    
    Returns ingredients most users would have.
    """
    from alfred.db.client import get_service_client
    
    client = get_service_client()
    
    # Common staples by name
    staple_names = [
        "olive oil", "salt", "black pepper", "garlic", "onion",
        "butter", "eggs", "milk", "flour", "sugar",
        "chicken breast", "rice", "pasta", "soy sauce", "tomatoes",
    ]
    
    staples = []
    for name in staple_names:
        try:
            result = client.table("ingredients").select(
                "id, name, category"
            ).ilike("name", f"%{name}%").limit(1).execute()
            
            if result.data:
                staples.append({
                    "id": result.data[0]["id"],
                    "name": result.data[0]["name"],
                    "category": result.data[0].get("category"),
                })
        except Exception as e:
            logger.debug(f"Staple lookup failed for {name}: {e}")
    
    return staples


def validate_pantry_items(items: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Validate pantry items before storing.
    
    Args:
        items: List of {name, category?, ingredient_id?}
    
    Returns:
        (valid_items, errors)
    """
    valid = []
    errors = []
    
    for item in items:
        if not item.get("name"):
            errors.append("Item missing name")
            continue
        
        valid.append({
            "name": item["name"].strip(),
            "category": item.get("category"),
            "ingredient_id": item.get("ingredient_id") or item.get("id"),
        })
    
    return valid, errors
