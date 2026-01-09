"""
Alfred V3 - Generic CRUD Tools.

Four tools that handle all database operations:
- db_read: Fetch rows with filters
- db_create: Insert new records
- db_update: Update existing records
- db_delete: Delete records

These replace the domain-specific tools (manage_inventory, query_recipe, etc.)
with a generic, table-agnostic approach.

Includes ingredient lookup layer for auto-linking items to the ingredients catalog.
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel

from alfred.db.client import get_client

logger = logging.getLogger(__name__)

# Tables that benefit from ingredient lookup (have name + ingredient_id fields)
INGREDIENT_LINKED_TABLES = {"inventory", "shopping_list", "recipe_ingredients"}


# =============================================================================
# Pydantic Models for Tool Parameters
# =============================================================================


class FilterClause(BaseModel):
    """A single filter condition for queries."""

    field: str
    op: Literal["=", "!=", "neq", ">", "<", ">=", "<=", "in", "not_in", "ilike", "is_null", "is_not_null", "contains"]
    value: Any  # For 'contains' on arrays: value is a single string to check


class DbReadParams(BaseModel):
    """Parameters for db_read.
    
    Filters are combined with AND. For OR logic, use `or_filters`:
    - filters: [A, B] → A AND B
    - or_filters: [C, D] → (C OR D)
    - filters: [A], or_filters: [C, D] → A AND (C OR D)
    """

    table: str
    filters: list[FilterClause] = []
    or_filters: list[FilterClause] = []  # Combined with OR, then AND'd with filters
    columns: list[str] | None = None  # None = all columns
    limit: int | None = None
    order_by: str | None = None
    order_dir: Literal["asc", "desc"] = "asc"


class DbCreateParams(BaseModel):
    """Parameters for db_create.
    
    Supports single record or batch create:
    - Single: {"name": "milk", "quantity": 2}
    - Batch: [{"name": "milk"}, {"name": "eggs"}]
    """

    table: str
    data: dict[str, Any] | list[dict[str, Any]]


class DbUpdateParams(BaseModel):
    """Parameters for db_update."""

    table: str
    filters: list[FilterClause]  # Required - no accidental full-table updates
    data: dict[str, Any]


class DbDeleteParams(BaseModel):
    """Parameters for db_delete."""

    table: str
    filters: list[FilterClause]  # Required - no accidental full-table deletes


# =============================================================================
# Tables that are user-scoped (auto-filter by user_id)
# Only parent tables with user_id column - child tables are filtered via FK
# =============================================================================

USER_OWNED_TABLES = {
    "inventory",
    "recipes",
    "recipe_ingredients",  # Denormalized user_id for simpler CRUD
    "meal_plans",
    "shopping_list",  # Note: singular, not plural
    "preferences",  # User preferences table
    "tasks",  # Transient task list
    "cooking_log",  # Cooking history
    "flavor_preferences",  # Ingredient usage tracking
}


# =============================================================================
# Filter Application Helper
# =============================================================================


def apply_filter(query: Any, f: FilterClause) -> Any:
    """Apply a single filter clause to a Supabase query."""
    match f.op:
        case "=":
            return query.eq(f.field, f.value)
        case "!=" | "neq":
            return query.neq(f.field, f.value)
        case ">":
            return query.gt(f.field, f.value)
        case "<":
            return query.lt(f.field, f.value)
        case ">=":
            return query.gte(f.field, f.value)
        case "<=":
            return query.lte(f.field, f.value)
        case "in":
            return query.in_(f.field, f.value)
        case "not_in":
            # Supabase doesn't have not_in, use neq for single or filter for multiple
            if isinstance(f.value, list) and len(f.value) == 1:
                return query.neq(f.field, f.value[0])
            # For multiple values, we'd need a workaround - for now, log warning
            import logging
            logging.getLogger("alfred.crud").warning(f"not_in with multiple values not fully supported: {f}")
            return query
        case "ilike":
            return query.ilike(f.field, f.value)
        case "is_null":
            return query.is_(f.field, "null")
        case "is_not_null":
            return query.not_.is_(f.field, "null")
        case "contains":
            # For array columns: check if array contains value
            # Uses PostgreSQL @> operator via Supabase .contains()
            return query.contains(f.field, [f.value] if isinstance(f.value, str) else f.value)
        case _:
            # Unknown operator - raise error instead of silently ignoring
            raise ValueError(f"Unsupported filter operator: {f.op}. Supported: =, !=, >, <, >=, <=, in, ilike, is_null, is_not_null, contains")
    return query


# =============================================================================
# CRUD Tool Implementations
# =============================================================================


async def db_read(params: DbReadParams, user_id: str) -> list[dict]:
    """
    Read rows from a table with filters.

    Args:
        params: Query parameters (table, filters, columns, limit, order)
        user_id: Current user's ID (auto-applied for user-owned tables)

    Returns:
        List of matching rows as dicts
    """
    client = get_client()

    # Build SELECT clause
    select_clause = ",".join(params.columns) if params.columns else "*"
    query = client.table(params.table).select(select_clause)

    # Auto-filter by user_id for user-owned tables
    if params.table in USER_OWNED_TABLES:
        query = query.eq("user_id", user_id)

    # Smart fuzzy matching for recipe name searches
    # Converts exact match to ilike with wildcards (LLM doesn't need to remember)
    filters_to_apply = list(params.filters)
    if params.table == "recipes":
        for i, f in enumerate(filters_to_apply):
            if f.field == "name" and f.op == "=":
                # Convert exact match to fuzzy match
                filters_to_apply[i] = FilterClause(
                    field="name",
                    op="ilike",
                    value=f"%{f.value}%"
                )

    # Apply explicit AND filters
    for f in filters_to_apply:
        query = apply_filter(query, f)

    # Apply OR filters (combined with OR, then AND'd with other filters)
    if params.or_filters:
        or_conditions = []
        for f in params.or_filters:
            # Build Supabase OR string: "field.op.value"
            if f.op == "=":
                or_conditions.append(f"{f.field}.eq.{f.value}")
            elif f.op == "ilike":
                or_conditions.append(f"{f.field}.ilike.{f.value}")
            elif f.op == "in":
                # in uses parentheses: field.in.(val1,val2)
                vals = ",".join(str(v) for v in f.value)
                or_conditions.append(f"{f.field}.in.({vals})")
            elif f.op == ">":
                or_conditions.append(f"{f.field}.gt.{f.value}")
            elif f.op == "<":
                or_conditions.append(f"{f.field}.lt.{f.value}")
            elif f.op == ">=":
                or_conditions.append(f"{f.field}.gte.{f.value}")
            elif f.op == "<=":
                or_conditions.append(f"{f.field}.lte.{f.value}")
            elif f.op == "is_null":
                if f.value:
                    or_conditions.append(f"{f.field}.is.null")
                else:
                    or_conditions.append(f"{f.field}.not.is.null")
        
        if or_conditions:
            query = query.or_(",".join(or_conditions))

    # Apply ordering
    if params.order_by:
        query = query.order(params.order_by, desc=(params.order_dir == "desc"))

    # Apply limit
    if params.limit:
        query = query.limit(params.limit)

    result = query.execute()
    return result.data


def _sanitize_uuid_fields(record: dict) -> dict:
    """
    Convert empty strings to None for UUID-type fields.
    
    Common UUID fields: id, user_id, recipe_id, meal_plan_id, ingredient_id, parent_recipe_id
    LLMs sometimes output "" instead of null for optional FK fields.
    """
    uuid_fields = {
        "id", "user_id", "recipe_id", "meal_plan_id", "ingredient_id",
        "parent_recipe_id", "from_meal_plan_id", "from_recipe_id"
    }
    sanitized = {}
    for key, value in record.items():
        if key in uuid_fields and value == "":
            sanitized[key] = None
        else:
            sanitized[key] = value
    return sanitized


async def db_create(params: DbCreateParams, user_id: str) -> dict | list[dict]:
    """
    Insert one or more rows into a table.

    Supports:
    - Single record: data = {"name": "milk", "quantity": 2}
    - Batch: data = [{"name": "milk"}, {"name": "eggs"}]

    For ingredient-linked tables (inventory, shopping_list, recipe_ingredients),
    automatically looks up and links ingredient_id based on name field.

    Args:
        params: Insert parameters (table, data or list of data)
        user_id: Current user's ID (auto-added for user-owned tables)

    Returns:
        Single dict for single insert, list of dicts for batch
    """
    client = get_client()

    # Normalize to list for processing
    is_batch = isinstance(params.data, list)
    records = params.data if is_batch else [params.data]
    
    # Sanitize UUID fields (empty string → None)
    records = [_sanitize_uuid_fields(rec) for rec in records]

    # Auto-link ingredient_id for ingredient-related tables
    if params.table in INGREDIENT_LINKED_TABLES:
        records = await _enrich_records_with_ingredient_ids(records)

    # Auto-add user_id for user-owned tables
    if params.table in USER_OWNED_TABLES:
        records = [{**rec, "user_id": user_id} for rec in records]

    result = client.table(params.table).insert(records).execute()
    
    # Return single or list based on input
    if is_batch:
        return result.data if result.data else []
    else:
        return result.data[0] if result.data else {}


async def db_update(params: DbUpdateParams, user_id: str) -> list[dict]:
    """
    Update rows matching filters.

    Args:
        params: Update parameters (table, filters, data)
        user_id: Current user's ID (auto-applied for user-owned tables)

    Returns:
        List of updated rows
    """
    client = get_client()

    query = client.table(params.table).update(params.data)

    # Auto-filter by user_id for user-owned tables (security)
    if params.table in USER_OWNED_TABLES:
        query = query.eq("user_id", user_id)

    # Apply explicit filters
    for f in params.filters:
        query = apply_filter(query, f)

    result = query.execute()
    return result.data


async def db_delete(params: DbDeleteParams, user_id: str) -> list[dict]:
    """
    Delete rows matching filters.

    Args:
        params: Delete parameters (table, filters)
        user_id: Current user's ID (auto-applied for user-owned tables)

    Returns:
        List of deleted rows
    """
    client = get_client()
    
    # Safety: Prevent empty-filter deletes on non-user-owned tables
    # (would result in DELETE with no WHERE clause → blocked by Supabase)
    if params.table not in USER_OWNED_TABLES and not params.filters:
        raise ValueError(
            f"Cannot delete from '{params.table}' with empty filters. "
            f"This table doesn't have user_id, so you must specify filters "
            f"(e.g., recipe_id for recipe_ingredients)."
        )

    # Build delete query
    query = client.table(params.table).delete()

    # Auto-filter by user_id for user-owned tables (security)
    if params.table in USER_OWNED_TABLES:
        query = query.eq("user_id", user_id)

    # Apply explicit filters
    for f in params.filters:
        query = apply_filter(query, f)

    # Execute - Supabase returns deleted rows in result.data
    result = query.execute()
    
    return result.data if result.data else []


# =============================================================================
# Ingredient Lookup Integration
# =============================================================================


async def _enrich_records_with_ingredient_ids(records: list[dict]) -> list[dict]:
    """
    Enrich records with ingredient_id by looking up names in the ingredients catalog.
    
    Uses high-confidence threshold (0.85) for writes - only auto-links on strong matches.
    Keeps original 'name' field as-is per user preference.
    """
    # Lazy import to avoid circular dependency
    try:
        from alfred.tools.ingredient_lookup import enrich_with_ingredient_id
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


# =============================================================================
# Tool Execution Dispatcher
# =============================================================================


async def execute_crud(
    tool: Literal["db_read", "db_create", "db_update", "db_delete"],
    params: dict[str, Any],
    user_id: str,
    registry: Any | None = None,
) -> Any:
    """
    Execute a CRUD tool by name.

    V4: If registry (SessionIdRegistry) provided, handles ID translation:
    - Filters: refs → UUIDs before execution
    - Output: UUIDs → refs before returning to LLM
    - Registry persists across turns (session-scoped)

    Args:
        tool: Tool name
        params: Tool parameters as a dict
        user_id: Current user's ID
        registry: SessionIdRegistry for ID translation (session-scoped)

    Returns:
        Tool result (with refs if registry provided, UUIDs otherwise)
    """
    # V4: Translate input refs to UUIDs
    if registry:
        params = _translate_input_params(tool, params, registry)
    
    # Sanitize data payloads - LLMs sometimes corrupt Unicode to NULL bytes
    # PostgreSQL rejects \u0000 in text fields
    if tool in ("db_create", "db_update") and "data" in params:
        params["data"] = _sanitize_payload(params["data"])
    
    # Execute the raw operation
    match tool:
        case "db_read":
            result = await db_read(DbReadParams(**params), user_id)
        case "db_create":
            result = await db_create(DbCreateParams(**params), user_id)
        case "db_update":
            result = await db_update(DbUpdateParams(**params), user_id)
        case "db_delete":
            result = await db_delete(DbDeleteParams(**params), user_id)
        case _:
            raise ValueError(f"Unknown tool: {tool}")
    
    # V4: Translate output UUIDs to refs
    if registry:
        result = _translate_output(tool, result, params.get("table", ""), registry)
    
    return result


def _translate_input_params(
    tool: str,
    params: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """
    Translate refs to UUIDs in CRUD parameters before execution.
    
    Handles:
    - Filter values (db_read, db_update, db_delete)
    - Payload FK fields (db_create, db_update)
    """
    params = params.copy()
    table = params.get("table", "")
    
    # Translate filters
    if "filters" in params and params["filters"]:
        raw_filters = params["filters"]
        # Convert dicts to FilterClause format for translation
        translated = registry.translate_filters([
            f if isinstance(f, dict) else f.model_dump() if hasattr(f, 'model_dump') else {"field": "", "op": "=", "value": ""}
            for f in raw_filters
        ])
        params["filters"] = translated
    
    if "or_filters" in params and params["or_filters"]:
        params["or_filters"] = registry.translate_filters([
            f if isinstance(f, dict) else f.model_dump() if hasattr(f, 'model_dump') else {"field": "", "op": "=", "value": ""}
            for f in params["or_filters"]
        ])
    
    # Translate payload FK fields
    if "data" in params:
        data = params["data"]
        if isinstance(data, list):
            params["data"] = registry.translate_payload_batch(data, table)
        elif isinstance(data, dict):
            params["data"] = registry.translate_payload(data, table)
    
    return params


def _translate_output(
    tool: str,
    result: Any,
    table: str,
    registry: Any,
) -> Any:
    """
    Translate UUIDs to refs in CRUD output before returning to LLM.
    """
    if tool == "db_read":
        # Read returns list of records - translate all IDs
        if isinstance(result, list):
            return registry.translate_read_output(result, table)
    
    elif tool == "db_create":
        # Create returns single dict or list of dicts with new IDs
        # Also translate FK fields that we have mappings for
        fk_fields = registry._get_fk_fields(table)
        
        if isinstance(result, dict):
            # Single record
            result = result.copy()
            if "id" in result:
                entity_type = registry._table_to_type(table)
                # Extract label for pending artifact matching
                label = result.get("name") or result.get("title")
                ref = registry.register_created(None, result["id"], entity_type, label=label)
                result["id"] = ref
            # Translate FK fields
            for fk_field in fk_fields:
                if fk_field in result and result[fk_field]:
                    fk_uuid = str(result[fk_field])
                    if fk_uuid in registry.uuid_to_ref:
                        result[fk_field] = registry.uuid_to_ref[fk_uuid]
            return result
        elif isinstance(result, list):
            # Batch create
            translated = []
            entity_type = registry._table_to_type(table)
            for record in result:
                if isinstance(record, dict):
                    record = record.copy()
                    if "id" in record:
                        # Extract label for pending artifact matching
                        label = record.get("name") or record.get("title")
                        ref = registry.register_created(None, record["id"], entity_type, label=label)
                        record["id"] = ref
                    # Translate FK fields
                    for fk_field in fk_fields:
                        if fk_field in record and record[fk_field]:
                            fk_uuid = str(record[fk_field])
                            if fk_uuid in registry.uuid_to_ref:
                                record[fk_field] = registry.uuid_to_ref[fk_uuid]
                translated.append(record)
            return translated
    
    elif tool == "db_update":
        # Update returns list of updated records
        if isinstance(result, list):
            return registry.translate_read_output(result, table)
    
    elif tool == "db_delete":
        # Delete returns list of deleted records
        if isinstance(result, list):
            return registry.translate_read_output(result, table)
    
    return result


def _sanitize_payload(data: dict | list) -> dict | list:
    """
    Sanitize data payload before database operations.
    
    LLMs sometimes corrupt Unicode characters to NULL bytes (\u0000).
    PostgreSQL rejects NULL bytes in text fields with error:
    '\\u0000 cannot be converted to text.'
    
    This strips NULL bytes from all string values.
    """
    if isinstance(data, list):
        return [_sanitize_payload(item) for item in data]
    elif isinstance(data, dict):
        return {k: _sanitize_value(v) for k, v in data.items()}
    return data


def _sanitize_value(value: Any) -> Any:
    """Sanitize a single value, recursing into nested structures."""
    if isinstance(value, str):
        # Remove NULL bytes that LLMs sometimes produce
        return value.replace("\x00", "")
    elif isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    elif isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    return value

