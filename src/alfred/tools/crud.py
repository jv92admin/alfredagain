"""
Alfred V3 - Generic CRUD Tools.

Four tools that handle all database operations:
- db_read: Fetch rows with filters (including semantic search via _semantic filter)
- db_create: Insert new records
- db_update: Update existing records
- db_delete: Delete records

These replace the domain-specific tools (manage_inventory, query_recipe, etc.)
with a generic, table-agnostic approach.

Includes:
- Ingredient lookup layer for auto-linking items to the ingredients catalog
- Semantic search for recipes via pgvector embeddings
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel

from alfred.db.client import get_client

logger = logging.getLogger(__name__)


# =============================================================================
# Semantic Search Configuration
# =============================================================================

# Tables that support semantic search (have embedding column)
SEMANTIC_SEARCH_TABLES = {"recipes"}

# Default settings for semantic search
SEMANTIC_DEFAULTS = {
    "max_distance": 0.7,  # Cosine distance threshold (lower = stricter, 0.7 = reasonable balance)
    "limit": 20,  # Max results from semantic search
}

# Tables that benefit from ingredient lookup (have name + ingredient_id fields)
INGREDIENT_LINKED_TABLES = {"inventory", "shopping_list", "recipe_ingredients"}


# =============================================================================
# Pydantic Models for Tool Parameters
# =============================================================================


class FilterClause(BaseModel):
    """A single filter condition for queries.
    
    Special filter for semantic search:
        field="_semantic", op="similar", value="light summer dinner"
    Only works for tables with embeddings (currently: recipes).
    """

    field: str
    op: Literal["=", "!=", "neq", ">", "<", ">=", "<=", "in", "not_in", "ilike", "is_null", "is_not_null", "contains", "similar"]
    value: Any  # For 'contains' on arrays: value is a single string to check; for 'similar': natural language query


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
# Semantic Search Helper
# =============================================================================


async def _semantic_search_recipes(
    query: str,
    user_id: str,
    limit: int = 20,
    max_distance: float = 0.6,
) -> list[str]:
    """
    Perform semantic search on recipes using pgvector embeddings.
    
    Returns list of recipe IDs that semantically match the query.
    Used by db_read when a _semantic filter is present.
    
    Args:
        query: Natural language query (e.g., "light summer dinner")
        user_id: Filter to user's recipes
        limit: Max results to return
        max_distance: Cosine distance threshold (0-1, lower = stricter)
    
    Returns:
        List of recipe UUIDs that match semantically
    """
    from alfred.tools.ingredient_lookup import generate_embedding
    
    client = get_client()
    
    try:
        # Generate embedding for the query
        query_embedding = generate_embedding(query)
        
        # Call the Postgres semantic match function
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
    filters: list[FilterClause],
) -> tuple[list[FilterClause], str | None]:
    """
    Extract _semantic filter from filter list.
    
    Returns:
        (remaining_filters, semantic_query or None)
    """
    remaining = []
    semantic_query = None
    
    for f in filters:
        if f.field == "_semantic":
            semantic_query = f.value
        else:
            remaining.append(f)
    
    return remaining, semantic_query


# =============================================================================
# CRUD Tool Implementations
# =============================================================================


async def db_read(params: DbReadParams, user_id: str) -> list[dict]:
    """
    Read rows from a table with filters.
    
    Supports semantic search via special `_semantic` filter:
        filters=[{"field": "_semantic", "op": "similar", "value": "light summer dinner"}]
    
    Currently semantic search is supported for: recipes

    Args:
        params: Query parameters (table, filters, columns, limit, order)
        user_id: Current user's ID (auto-applied for user-owned tables)

    Returns:
        List of matching rows as dicts
    """
    client = get_client()
    
    # Extract semantic filter (if present)
    filters_to_apply, semantic_query = _extract_semantic_filter(list(params.filters))
    
    # Handle semantic search for supported tables
    semantic_ids: list[str] | None = None
    if semantic_query and params.table in SEMANTIC_SEARCH_TABLES:
        semantic_ids = await _semantic_search_recipes(
            query=semantic_query,
            user_id=user_id,
            limit=SEMANTIC_DEFAULTS["limit"],
            max_distance=SEMANTIC_DEFAULTS["max_distance"],
        )
        
        # If semantic search returns nothing, return empty (no matches for this intent)
        if not semantic_ids:
            logger.info(f"Semantic search returned no results for '{semantic_query}'")
            return []
    elif semantic_query and params.table not in SEMANTIC_SEARCH_TABLES:
        logger.warning(f"Semantic search not supported for table '{params.table}', ignoring _semantic filter")

    # Build SELECT clause
    select_clause = ",".join(params.columns) if params.columns else "*"
    
    # Auto-include recipe_ingredients for recipe reads (essential context for planning)
    # This gives us ingredient names + categories for grouping, without needing prompts to specify nested syntax
    if params.table == "recipes" and "recipe_ingredients" not in select_clause:
        select_clause += ", recipe_ingredients(name, category)"

    # Auto-include ingredient metadata for inventory/shopping reads
    # This flows parent_category, family, tier, cuisines into LLM context
    if params.table in INGREDIENT_LINKED_TABLES and "ingredients(" not in select_clause:
        select_clause += ", ingredients(parent_category, family, tier, cuisines)"
    
    query = client.table(params.table).select(select_clause)

    # Auto-filter by user_id for user-owned tables
    if params.table in USER_OWNED_TABLES:
        query = query.eq("user_id", user_id)
    
    # Apply semantic ID filter (restricts to semantically matched records)
    if semantic_ids:
        query = query.in_("id", semantic_ids)

    # Smart fuzzy matching for recipe name searches
    # Converts exact match to ilike with wildcards (LLM doesn't need to remember)
    if params.table == "recipes":
        for i, f in enumerate(filters_to_apply):
            if f.field == "name" and f.op == "=":
                # Convert exact match to fuzzy match
                filters_to_apply[i] = FilterClause(
                    field="name",
                    op="ilike",
                    value=f"%{f.value}%"
                )

    # Smart ingredient matching for inventory/shopping searches
    # - op "=" → exact match (best single candidate)
    # - op "similar" → multi match (top 5 candidates)
    ingredient_ids_to_include: list[str] = []
    if params.table in ("inventory", "shopping_list"):
        from alfred.tools.ingredient_lookup import lookup_ingredient
        
        for f in filters_to_apply:
            if f.field == "name" and f.op in ("=", "similar"):
                search_term = str(f.value).strip("%").strip()
                if search_term:
                    # "=" = exact (limit 1), "similar" = multi (limit 5)
                    limit = 1 if f.op == "=" else 5
                    matches = await lookup_ingredient(search_term, limit=limit)
                    
                    # Handle single vs multi return
                    if matches:
                        if isinstance(matches, list):
                            for match in matches:
                                ingredient_ids_to_include.append(match.id)
                                logger.info(f"Similar search '{search_term}' → '{match.name}'")
                        else:
                            ingredient_ids_to_include.append(matches.id)
                            logger.info(f"Exact search '{search_term}' → '{matches.name}'")

    # For inventory/shopping: remove name filters that were processed by ingredient lookup
    # These used "similar" or "=" ops which apply_filter doesn't handle
    if params.table in ("inventory", "shopping_list"):
        filters_to_apply = [
            f for f in filters_to_apply 
            if not (f.field == "name" and f.op in ("=", "similar"))
        ]
    
    # Apply explicit AND filters (remaining filters after ingredient lookup removal)
    for f in filters_to_apply:
        query = apply_filter(query, f)
    
    # For inventory with ingredient matches: add OR condition for ingredient_id
    if ingredient_ids_to_include and params.table == "inventory":
        # Combine name filter with ingredient_id match using OR
        id_list = ",".join(ingredient_ids_to_include)
        query = query.or_(f"ingredient_id.in.({id_list})")

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


def _deduplicate_batch(records: list[dict], table: str) -> list[dict]:
    """
    Remove duplicate records from a batch insert.

    For ingredient-linked tables, dedup by ingredient_id (or name fallback).
    Keeps last occurrence (later entry may have updated quantities).
    """
    if table not in INGREDIENT_LINKED_TABLES or len(records) <= 1:
        return records

    seen: dict[str, int] = {}  # dedup_key -> index of last occurrence
    for idx, rec in enumerate(records):
        key = rec.get("ingredient_id") or (rec.get("name", "").lower().strip() or None)
        if not key:
            continue  # No dedup key available, keep unconditionally
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

    # Deduplicate batch records (prevents same-item collisions from LLM output)
    if is_batch:
        records = _deduplicate_batch(records, params.table)

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
# Read Rerouting via Unified Entity Data Access (V9)
# =============================================================================


def _extract_refs_from_filters(filters: list) -> list[str]:
    """Extract entity refs from ID filters."""
    refs = []
    for f in filters:
        f_dict = f if isinstance(f, dict) else (f.model_dump() if hasattr(f, 'model_dump') else {})
        field = f_dict.get("field", "")
        op = f_dict.get("op", "")
        value = f_dict.get("value")

        if field != "id":
            continue

        if op == "=" and isinstance(value, str):
            refs.append(value)
        elif op == "in" and isinstance(value, list):
            refs.extend(v for v in value if isinstance(v, str))

    return refs


def _try_reroute_pending_read(
    params: dict[str, Any],
    registry: Any,
) -> list[dict] | None:
    """
    Check if db_read references entities with registry data and reroute.

    Uses the unified get_entity_data() method to check if data is available
    in the registry. This works for any entity type - the registry determines
    what data it has available.

    This enables:
    - "read gen_recipe_1" to work even though it's not in the database
    - Uniform mental model: "need data? read it" (works for both DB and generated content)
    - Entities can fade from Active Entities and still be retrievable

    Returns:
        - List of entity dicts if ALL refs have registry data
        - None if ANY ref needs DB lookup (proceed with normal db_read)
    """
    filters = params.get("filters", [])
    if not filters:
        return None

    refs = _extract_refs_from_filters(filters)
    if not refs:
        return None

    # Check each ref using unified method
    results = []
    for ref in refs:
        # UNIFIED: Use single method for all refs
        data = registry.get_entity_data(ref)
        if data is not None:
            # Format to match db_read shape (add id field with ref)
            result = data.copy() if isinstance(data, dict) else {"data": data}
            result["id"] = ref  # Use the ref as ID (LLM-facing)
            results.append(result)
            logger.info(f"Read rerouting: {ref} → returned from registry")
        else:
            # Any ref without registry data = need DB lookup
            # Can't mix registry and DB results, so go to DB for all
            return None

    return results if results else None


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
    # V8: Read rerouting for gen_* refs (MUST be BEFORE translation!)
    # If reading a gen_* ref that has __pending__ UUID, return from pending_artifacts.
    # This check needs the original refs (gen_recipe_1), not translated UUIDs.
    if tool == "db_read" and registry:
        rerouted = _try_reroute_pending_read(params, registry)
        if rerouted is not None:
            return rerouted

    # V4: Translate input refs to UUIDs (after read rerouting check)
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
        
        # V5: Enrich lazy-registered FK refs with names
        await _enrich_lazy_registrations(registry, user_id)
        
        # V5: Post-process to add labels that were just enriched
        result = _add_enriched_labels(result, params.get("table", ""), registry)
    
    return result


def _add_enriched_labels(result: Any, table: str, registry: Any) -> Any:
    """
    Post-process result to add FK labels that were just enriched.
    
    This runs AFTER enrichment to ensure newly-fetched labels are included.
    """
    if not result:
        return result
    
    fk_fields = registry._get_fk_fields(table)
    if not fk_fields:
        return result
    
    def add_labels_to_record(record: dict) -> dict:
        record = record.copy()
        for fk_field in fk_fields:
            fk_ref = record.get(fk_field)
            label_field = f"_{fk_field}_label"
            # Only add if we have a ref and don't already have the label
            if fk_ref and label_field not in record:
                fk_label = registry.ref_labels.get(fk_ref)
                if fk_label and fk_label != fk_ref:
                    record[label_field] = fk_label
        return record
    
    if isinstance(result, list):
        return [add_labels_to_record(r) if isinstance(r, dict) else r for r in result]
    elif isinstance(result, dict):
        return add_labels_to_record(result)
    
    return result


async def _enrich_lazy_registrations(registry: Any, user_id: str) -> None:
    """
    Fetch names for lazy-registered FK refs.
    
    When a db_read returns records with FK fields (e.g., meal_plans with recipe_id),
    we lazy-register those FKs to prevent UUID leakage. This function batch-fetches
    the actual names so displays show "Butter Chicken" instead of "recipe_1".
    
    Generic across all FK types: recipes, ingredients, tasks, etc.
    """
    enrich_queue = registry.get_lazy_enrich_queue()
    if not enrich_queue:
        return
    
    # Group by table for batch queries
    from collections import defaultdict
    by_table: dict[str, list[tuple[str, str, str]]] = defaultdict(list)  # table -> [(ref, name_col, uuid)]
    for ref, (table, name_col, uuid) in enrich_queue.items():
        by_table[table].append((ref, name_col, uuid))
    
    enrichments: dict[str, str] = {}
    
    for table, items in by_table.items():
        if not items:
            continue
        
        # Get all UUIDs for this table
        uuids = [uuid for _, _, uuid in items]
        name_col = items[0][1]  # All items for same table have same name_col
        
        try:
            # Batch query for names - use raw db_read since we already have UUIDs
            result = await db_read(
                DbReadParams(
                    table=table,
                    filters=[{"field": "id", "op": "in", "value": uuids}],
                    columns=["id", name_col],
                ),
                user_id,
            )
            
            # Build UUID → name map
            uuid_to_name = {str(r["id"]): r.get(name_col) for r in result if r.get(name_col)}
            
            # Map back to refs
            for ref, _, uuid in items:
                if uuid in uuid_to_name:
                    enrichments[ref] = uuid_to_name[uuid]
                    
        except Exception as e:
            logger.warning(f"Failed to enrich lazy registrations for {table}: {e}")
    
    # Apply all enrichments
    if enrichments:
        registry.apply_enrichment(enrichments)
    else:
        registry.clear_enrich_queue()


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
            # Translate FK fields and add labels
            for fk_field in fk_fields:
                if fk_field in result and result[fk_field]:
                    fk_uuid = str(result[fk_field])
                    if fk_uuid in registry.uuid_to_ref:
                        fk_ref = registry.uuid_to_ref[fk_uuid]
                        result[fk_field] = fk_ref
                        # V5: Add label for display enrichment
                        fk_label = registry.ref_labels.get(fk_ref)
                        if fk_label and fk_label != fk_ref:
                            result[f"_{fk_field}_label"] = fk_label
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
                    # Translate FK fields and add labels
                    for fk_field in fk_fields:
                        if fk_field in record and record[fk_field]:
                            fk_uuid = str(record[fk_field])
                            if fk_uuid in registry.uuid_to_ref:
                                fk_ref = registry.uuid_to_ref[fk_uuid]
                                record[fk_field] = fk_ref
                                # V5: Add label for display enrichment
                                fk_label = registry.ref_labels.get(fk_ref)
                                if fk_label and fk_label != fk_ref:
                                    record[f"_{fk_field}_label"] = fk_label
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

