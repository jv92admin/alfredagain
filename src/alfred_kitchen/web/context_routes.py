"""
Context API endpoints for @-mention autocomplete.

Provides entity search across all types for the chat input autocomplete.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from alfred_kitchen.db.client import get_authenticated_client
from alfred_kitchen.web.auth import AuthenticatedUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])


# =============================================================================
# Response Models
# =============================================================================


class EntityItem(BaseModel):
    """Single entity for autocomplete."""
    id: str  # UUID
    label: str


class EntityGroup(BaseModel):
    """Group of entities by type."""
    type: str  # Short type: recipe, inv, shop, meal, task
    label: str  # Display label: Recipes, Inventory, etc.
    items: list[EntityItem]


class EntitySearchResponse(BaseModel):
    """Grouped search results for autocomplete."""
    groups: list[EntityGroup]


# =============================================================================
# Entity Type Configuration
# =============================================================================

# Priority order for display (most relevant first)
# Note: meal_plans excluded - no descriptive name column (only date + meal_type)
ENTITY_TYPES = [
    {"type": "recipe", "table": "recipes", "label": "Recipes", "name_field": "name"},
    {"type": "inv", "table": "inventory", "label": "Inventory", "name_field": "name"},
    {"type": "shop", "table": "shopping_list", "label": "Shopping List", "name_field": "name"},
    {"type": "task", "table": "tasks", "label": "Tasks", "name_field": "title"},
]

LIMIT_PER_TYPE = 5
TOTAL_LIMIT = 15


# =============================================================================
# Search Endpoint
# =============================================================================


@router.get("/entities", response_model=EntitySearchResponse)
async def search_entities(
    user: AuthenticatedUser = Depends(get_current_user),
    q: str = Query("", description="Search query (empty returns recent)"),
) -> EntitySearchResponse:
    """
    Search entities across all types for @-mention autocomplete.

    Returns results grouped by entity type in priority order.
    Empty query returns recent entities from each type.
    """
    client = get_authenticated_client(user.access_token)
    groups: list[EntityGroup] = []
    total_count = 0

    for entity_config in ENTITY_TYPES:
        if total_count >= TOTAL_LIMIT:
            break

        remaining = min(LIMIT_PER_TYPE, TOTAL_LIMIT - total_count)

        try:
            query = client.table(entity_config["table"]).select("id, " + entity_config["name_field"])

            if q.strip():
                # ILIKE search on name field
                query = query.ilike(entity_config["name_field"], f"%{q}%")

            # Order by most recent, limit results
            result = query.order("created_at", desc=True).limit(remaining).execute()

            if result.data:
                items = [
                    EntityItem(
                        id=str(row["id"]),
                        label=row[entity_config["name_field"]] or "(unnamed)"
                    )
                    for row in result.data
                ]

                groups.append(EntityGroup(
                    type=entity_config["type"],
                    label=entity_config["label"],
                    items=items
                ))

                total_count += len(items)

        except Exception as e:
            logger.warning(f"Search failed for {entity_config['table']}: {e}")
            continue

    return EntitySearchResponse(groups=groups)
