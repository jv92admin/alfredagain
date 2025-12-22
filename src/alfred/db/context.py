"""
Alfred V2 - Context Retrieval.

Hybrid SQL + vector retrieval for intelligent context building.
"""

from alfred.db import client as db


async def get_context(
    user_id: str,
    needs: list[str],
    query: str | None = None,
) -> dict:
    """
    Retrieve context based on what the current task needs.

    This is the main entry point for context retrieval.
    The Router determines what context is needed, and this function
    fetches it efficiently.

    Args:
        user_id: Current user's ID
        needs: List of context types needed (from RouterOutput.context_needs)
               Valid values: "inventory", "preferences", "recipes", "meal_plans", "shopping_list"
        query: Optional search query for semantic retrieval

    Returns:
        Dictionary with requested context

    Example:
        context = await get_context(
            user_id="abc-123",
            needs=["inventory", "preferences"],
            query="chicken recipes",
        )
    """
    context: dict = {}

    # Parallel fetch based on needs
    if "inventory" in needs:
        context["inventory"] = await db.get_inventory(user_id)

    if "preferences" in needs:
        context["preferences"] = await db.get_preferences(user_id)

    if "recipes" in needs:
        # For now, just get user's recipes
        # TODO: Add vector search when query is provided
        context["recipes"] = await db.get_recipes(user_id, limit=10)

    if "meal_plans" in needs:
        # Get upcoming week
        from datetime import date, timedelta

        today = date.today()
        week_later = today + timedelta(days=7)
        context["meal_plans"] = await db.get_meal_plans(
            user_id, today.isoformat(), week_later.isoformat()
        )

    if "shopping_list" in needs:
        context["shopping_list"] = await db.get_shopping_list(user_id)

    return context


async def search_ingredients(query: str, limit: int = 10) -> list[dict]:
    """
    Search for ingredients by name or alias.

    For MVP, uses simple text search.
    TODO: Add vector search for semantic matching.
    """
    return await db.get_ingredients(search=query, limit=limit)


async def search_recipes(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """
    Search for recipes.

    For MVP, uses simple text search.
    TODO: Add vector search for semantic matching.
    """
    # For now, just get all and filter client-side
    # This is inefficient but fine for MVP
    recipes = await db.get_recipes(user_id, limit=50)

    query_lower = query.lower()
    matching = [
        r
        for r in recipes
        if query_lower in r.get("name", "").lower()
        or query_lower in r.get("cuisine", "").lower()
        or any(query_lower in tag.lower() for tag in r.get("tags", []))
    ]

    return matching[:limit]

