"""
Schema API endpoints.

Exposes backend schema infrastructure to the frontend for schema-driven UI.
"""

from fastapi import APIRouter, HTTPException

from alfred.tools.schema import SUBDOMAIN_REGISTRY, FIELD_ENUMS
from alfred.models.entities import (
    InventoryCreate,
    InventoryUpdate,
    RecipeCreate,
    RecipeIngredientCreate,
    MealPlanCreate,
    ShoppingListItemCreate,
    TaskCreate,
)

router = APIRouter(prefix="/schema", tags=["schema"])


# =============================================================================
# Model Registry - Maps subdomains to Pydantic models
# =============================================================================

MODEL_REGISTRY: dict[str, dict[str, type | None]] = {
    "inventory": {
        "create": InventoryCreate,
        "update": InventoryUpdate,
    },
    "recipes": {
        "create": RecipeCreate,
        "update": None,  # Complex update, custom handling
    },
    "meal_plans": {
        "create": MealPlanCreate,
        "update": None,
    },
    "shopping": {
        "create": ShoppingListItemCreate,
        "update": None,
    },
    "tasks": {
        "create": TaskCreate,
        "update": None,
    },
}


# =============================================================================
# Helpers
# =============================================================================


def _collect_enums(subdomain: str, tables: list[str]) -> dict[str, list[str]]:
    """
    Collect enum values for a subdomain, deduping when subdomain == table name.

    FIELD_ENUMS is nested: {key: {field: values}} where key can be subdomain or table name.
    Often subdomain name matches primary table (e.g., "inventory"), so we avoid double lookup.
    """
    enums: dict[str, list[str]] = dict(FIELD_ENUMS.get(subdomain, {}))

    # Only lookup tables that differ from subdomain name
    for table in tables:
        if table != subdomain:
            table_enums = FIELD_ENUMS.get(table, {})
            for field, values in table_enums.items():
                if field not in enums:
                    enums[field] = values

    return enums


# =============================================================================
# Schema Endpoints
# =============================================================================


@router.get("")
def get_all_schemas():
    """
    Get overview of all subdomains.

    Returns subdomain names and their associated tables.
    """
    subdomains = {}
    for name, config in SUBDOMAIN_REGISTRY.items():
        tables = config.get("tables", [])
        subdomains[name] = {
            "tables": tables,
            "primary": tables[0] if tables else None,
        }

    return {"subdomains": subdomains}


@router.get("/{subdomain}")
def get_subdomain_schema(subdomain: str):
    """
    Get full schema for a subdomain.

    Returns:
    - tables: List of tables in this subdomain
    - enums: Field enum values for dropdowns
    """
    if subdomain not in SUBDOMAIN_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown subdomain: {subdomain}")

    config = SUBDOMAIN_REGISTRY[subdomain]
    tables = config.get("tables", [])
    enums = _collect_enums(subdomain, tables)

    return {
        "subdomain": subdomain,
        "tables": tables,
        "enums": enums,
    }


@router.get("/{subdomain}/form")
def get_form_schema(subdomain: str):
    """
    Get Pydantic JSON Schema for create/update forms.

    Returns:
    - create: JSON Schema for create form
    - update: JSON Schema for update form (if available)
    - enums: Field enum values for dropdowns
    """
    if subdomain not in SUBDOMAIN_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown subdomain: {subdomain}")

    models = MODEL_REGISTRY.get(subdomain)
    if not models:
        raise HTTPException(
            status_code=404,
            detail=f"No form models registered for subdomain: {subdomain}"
        )

    tables = SUBDOMAIN_REGISTRY[subdomain].get("tables", [])
    enums = _collect_enums(subdomain, tables)

    create_schema = None
    update_schema = None

    if models.get("create"):
        create_schema = models["create"].model_json_schema()

    if models.get("update"):
        update_schema = models["update"].model_json_schema()

    return {
        "create": create_schema,
        "update": update_schema,
        "enums": enums,
    }
