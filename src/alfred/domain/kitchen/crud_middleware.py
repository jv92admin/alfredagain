"""
Kitchen CRUD Middleware.

Domain-specific CRUD intelligence for the kitchen domain:
- Semantic search for recipes via pgvector embeddings
- Auto-include nested relations (recipe_ingredients, ingredients)
- Fuzzy name matching for recipe searches
- Ingredient catalog lookup for inventory/shopping searches
- Ingredient ID enrichment for writes
- Batch deduplication by ingredient_id
"""

import logging
from typing import Any

from alfred.domain.base import CRUDMiddleware, ReadPreprocessResult

logger = logging.getLogger(__name__)


# =============================================================================
# Kitchen-Specific Constants
# =============================================================================

# Tables that support semantic search (have embedding column)
SEMANTIC_SEARCH_TABLES = {"recipes"}

# Default settings for semantic search
SEMANTIC_DEFAULTS = {
    "max_distance": 0.7,
    "limit": 20,
}

# Tables that benefit from ingredient lookup (have name + ingredient_id fields)
INGREDIENT_LINKED_TABLES = {"inventory", "shopping_list", "recipe_ingredients"}

# Tables that are user-scoped (auto-filter by user_id)
USER_OWNED_TABLES = {
    "inventory",
    "recipes",
    "recipe_ingredients",
    "meal_plans",
    "shopping_list",
    "preferences",
    "tasks",
    "cooking_log",
    "flavor_preferences",
}

# FK field names containing UUIDs (for empty string → None sanitization)
UUID_FIELDS = {
    "id", "user_id", "recipe_id", "meal_plan_id", "ingredient_id",
    "parent_recipe_id", "from_meal_plan_id", "from_recipe_id",
}


# =============================================================================
# Semantic Search
# =============================================================================


async def _semantic_search_recipes(
    query: str,
    user_id: str,
    limit: int = 20,
    max_distance: float = 0.6,
) -> list[str]:
    """
    Perform semantic search on recipes using pgvector embeddings.

    Returns list of recipe UUIDs that semantically match the query.
    """
    from alfred.db.client import get_client
    from alfred.domain.kitchen.tools.ingredient_lookup import generate_embedding

    client = get_client()

    try:
        query_embedding = generate_embedding(query)
        result = client.rpc(
            "match_recipe_semantic",
            {
                "query_embedding": query_embedding,
                "user_id_filter": user_id,
                "limit_n": limit,
                "max_distance": max_distance,
            }
        ).execute()

        if result.data:
            ids = [row["id"] for row in result.data]
            logger.info(f"Semantic search '{query}' found {len(ids)} recipes")
            return ids

        logger.info(f"Semantic search '{query}' found no matches")
        return []

    except Exception as e:
        logger.warning(f"Semantic search failed, falling back to empty: {e}")
        return []


def _extract_semantic_filter(
    filters: list,
) -> tuple[list, str | None]:
    """Extract _semantic filter from filter list."""
    remaining = []
    semantic_query = None

    for f in filters:
        if f.field == "_semantic":
            semantic_query = f.value
        else:
            remaining.append(f)

    return remaining, semantic_query


# =============================================================================
# Ingredient Enrichment for Writes
# =============================================================================


async def _enrich_records_with_ingredient_ids(records: list[dict]) -> list[dict]:
    """
    Enrich records with ingredient_id by looking up names in the ingredients catalog.

    Uses high-confidence threshold (0.85) for writes — only auto-links on strong matches.
    """
    try:
        from alfred.domain.kitchen.tools.ingredient_lookup import enrich_with_ingredient_id
    except ImportError:
        logger.warning("ingredient_lookup module not available, skipping enrichment")
        return records

    enriched = []
    for record in records:
        try:
            enriched_record = await enrich_with_ingredient_id(record, operation="write")
            enriched.append(enriched_record)
        except Exception as e:
            logger.warning(f"Failed to enrich record with ingredient_id: {e}")
            enriched.append(record)

    return enriched


def _deduplicate_batch(records: list[dict], table: str) -> list[dict]:
    """
    Remove duplicate records from a batch insert.

    For ingredient-linked tables, dedup by ingredient_id (or name fallback).
    Keeps last occurrence (later entry may have updated quantities).
    """
    if table not in INGREDIENT_LINKED_TABLES or len(records) <= 1:
        return records

    seen: dict[str, int] = {}
    for idx, rec in enumerate(records):
        key = rec.get("ingredient_id") or (rec.get("name", "").lower().strip() or None)
        if not key:
            continue
        if key in seen:
            prev_name = records[seen[key]].get("name", key)
            logger.warning(
                "Batch dedup: duplicate '%s' at positions %d and %d in %s, keeping last",
                prev_name, seen[key], idx, table,
            )
        seen[key] = idx

    keep_indices = set(seen.values())
    deduped = []
    for idx, rec in enumerate(records):
        key = rec.get("ingredient_id") or (rec.get("name", "").lower().strip() or None)
        if not key or idx in keep_indices:
            deduped.append(rec)

    if len(deduped) < len(records):
        logger.warning(
            "Batch dedup: removed %d duplicates from %d records for %s",
            len(records) - len(deduped), len(records), table,
        )

    return deduped


# =============================================================================
# Kitchen CRUD Middleware
# =============================================================================


class KitchenCRUDMiddleware(CRUDMiddleware):
    """
    Kitchen-specific CRUD middleware.

    Provides:
    - Semantic search via pgvector for recipe discovery
    - Auto-include of nested relations (recipe_ingredients, ingredients metadata)
    - Fuzzy name matching for recipe searches
    - Ingredient catalog lookup for inventory/shopping name searches
    - Ingredient ID enrichment before writes
    - Batch deduplication by ingredient_id
    """

    async def pre_read(self, params: Any, user_id: str) -> ReadPreprocessResult:
        from alfred.tools.crud import FilterClause

        table = params.table
        filters = list(params.filters)
        select_additions: list[str] = []
        pre_filter_ids: list[str] | None = None
        or_conditions: list[str] | None = None

        # 1. Semantic search for recipes
        remaining_filters, semantic_query = _extract_semantic_filter(filters)
        if semantic_query and table in SEMANTIC_SEARCH_TABLES:
            ids = await _semantic_search_recipes(
                query=semantic_query,
                user_id=user_id,
                limit=SEMANTIC_DEFAULTS["limit"],
                max_distance=SEMANTIC_DEFAULTS["max_distance"],
            )
            if not ids:
                return ReadPreprocessResult(params=params, short_circuit_empty=True)
            pre_filter_ids = ids
            filters = remaining_filters
        elif semantic_query:
            logger.warning(
                f"Semantic search not supported for table '{table}', "
                f"ignoring _semantic filter"
            )
            filters = remaining_filters

        # 2. Auto-include nested relations
        if table == "recipes":
            select_additions.append("recipe_ingredients(name, category)")
        if table in INGREDIENT_LINKED_TABLES:
            select_additions.append(
                "ingredients(parent_category, family, tier, cuisines)"
            )

        # 3. Fuzzy name matching for recipe searches
        if table == "recipes":
            for i, f in enumerate(filters):
                if f.field == "name" and f.op == "=":
                    filters[i] = FilterClause(
                        field="name", op="ilike", value=f"%{f.value}%"
                    )

        # 4. Ingredient lookup for inventory/shopping name searches
        ingredient_ids: list[str] = []
        if table in ("inventory", "shopping_list"):
            from alfred.domain.kitchen.tools.ingredient_lookup import lookup_ingredient

            for f in filters:
                if f.field == "name" and f.op in ("=", "similar"):
                    search_term = str(f.value).strip("%").strip()
                    if search_term:
                        limit = 1 if f.op == "=" else 5
                        matches = await lookup_ingredient(search_term, limit=limit)
                        if matches:
                            if isinstance(matches, list):
                                for match in matches:
                                    ingredient_ids.append(match.id)
                                    logger.info(
                                        f"Similar search '{search_term}' → '{match.name}'"
                                    )
                            else:
                                ingredient_ids.append(matches.id)
                                logger.info(
                                    f"Exact search '{search_term}' → '{matches.name}'"
                                )

            # Remove name filters processed by ingredient lookup
            filters = [
                f for f in filters
                if not (f.field == "name" and f.op in ("=", "similar"))
            ]

        # 5. Build OR conditions for ingredient IDs
        if ingredient_ids and table == "inventory":
            id_list = ",".join(ingredient_ids)
            or_conditions = [f"ingredient_id.in.({id_list})"]

        # Rebuild params with modified filters
        from alfred.tools.crud import DbReadParams

        modified_params = DbReadParams(
            table=params.table,
            filters=filters,
            or_filters=params.or_filters,
            columns=params.columns,
            limit=params.limit,
            order_by=params.order_by,
            order_dir=params.order_dir,
        )

        return ReadPreprocessResult(
            params=modified_params,
            select_additions=select_additions,
            pre_filter_ids=pre_filter_ids,
            or_conditions=or_conditions,
        )

    async def pre_write(self, table: str, records: list[dict]) -> list[dict]:
        if table in INGREDIENT_LINKED_TABLES:
            records = await _enrich_records_with_ingredient_ids(records)
        return records

    def deduplicate_batch(self, table: str, records: list[dict]) -> list[dict]:
        return _deduplicate_batch(records, table)
