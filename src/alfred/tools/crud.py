"""
Alfred V2 - Generic CRUD Tools.

Four tools that handle all database operations:
- db_read: Fetch rows with filters
- db_create: Insert new records
- db_update: Update existing records
- db_delete: Delete records

These replace the domain-specific tools (manage_inventory, query_recipe, etc.)
with a generic, table-agnostic approach.
"""

from typing import Any, Literal

from pydantic import BaseModel

from alfred.db.client import get_client


# =============================================================================
# Pydantic Models for Tool Parameters
# =============================================================================


class FilterClause(BaseModel):
    """A single filter condition for queries."""

    field: str
    op: Literal["=", ">", "<", ">=", "<=", "in", "ilike", "is_null", "contains"]
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
        case "ilike":
            return query.ilike(f.field, f.value)
        case "is_null":
            return query.is_(f.field, "null")
        case "contains":
            # For array columns: check if array contains value
            # Uses PostgreSQL @> operator via Supabase .contains()
            return query.contains(f.field, [f.value] if isinstance(f.value, str) else f.value)
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

    # Apply explicit AND filters
    for f in params.filters:
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


async def db_create(params: DbCreateParams, user_id: str) -> dict | list[dict]:
    """
    Insert one or more rows into a table.

    Supports:
    - Single record: data = {"name": "milk", "quantity": 2}
    - Batch: data = [{"name": "milk"}, {"name": "eggs"}]

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


async def db_delete(params: DbDeleteParams, user_id: str) -> int:
    """
    Delete rows matching filters.

    Args:
        params: Delete parameters (table, filters)
        user_id: Current user's ID (auto-applied for user-owned tables)

    Returns:
        Count of deleted rows
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

    query = client.table(params.table).delete()

    # Auto-filter by user_id for user-owned tables (security)
    if params.table in USER_OWNED_TABLES:
        query = query.eq("user_id", user_id)

    # Apply explicit filters
    for f in params.filters:
        query = apply_filter(query, f)

    result = query.execute()
    return len(result.data)


# =============================================================================
# Tool Execution Dispatcher
# =============================================================================


async def execute_crud(
    tool: Literal["db_read", "db_create", "db_update", "db_delete"],
    params: dict[str, Any],
    user_id: str,
) -> Any:
    """
    Execute a CRUD tool by name.

    Args:
        tool: Tool name
        params: Tool parameters as a dict
        user_id: Current user's ID

    Returns:
        Tool result
    """
    match tool:
        case "db_read":
            return await db_read(DbReadParams(**params), user_id)
        case "db_create":
            return await db_create(DbCreateParams(**params), user_id)
        case "db_update":
            return await db_update(DbUpdateParams(**params), user_id)
        case "db_delete":
            return await db_delete(DbDeleteParams(**params), user_id)
        case _:
            raise ValueError(f"Unknown tool: {tool}")

