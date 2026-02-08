"""
Alfred Schema Generation System.

Provides:
- Helper functions for subdomain/table resolution
- Auto-generation of table schemas from database
- Schema caching for performance

Kitchen-specific constants (FIELD_ENUMS, SEMANTIC_NOTES, etc.) live in
alfred.domain.kitchen.schema. Access them via DomainConfig methods.
"""

import time
from typing import Any



# =============================================================================
# Domain-Aware Accessors
# =============================================================================
# Constants moved to alfred.domain.kitchen.schema (Phase 3a).
# Functions below access them through domain config.


def _get_domain():
    """Lazy import to avoid circular dependency."""
    from alfred.domain import get_current_domain
    return get_current_domain()


def _get_subdomain_registry():
    """Get SUBDOMAIN_REGISTRY from domain config."""
    return _get_domain().get_subdomain_registry()


def _get_subdomain_scope():
    """Get SUBDOMAIN_SCOPE from domain config."""
    return _get_domain().get_scope_config()


def get_subdomain_tables(subdomain: str) -> list[str]:
    """Get the list of tables for a subdomain."""
    registry = _get_subdomain_registry()
    config = registry.get(subdomain, {})
    if isinstance(config, dict):
        return config.get("tables", [])
    # Backwards compatibility if somehow still a list
    return config if isinstance(config, list) else []


def get_complexity_rules(subdomain: str) -> dict[str, str] | None:
    """Get complexity rules for a subdomain."""
    registry = _get_subdomain_registry()
    config = registry.get(subdomain, {})
    if isinstance(config, dict):
        return config.get("complexity_rules")
    return None


def get_persona_for_subdomain(subdomain: str, step_type: str = "crud") -> str:
    """Get the persona text for a subdomain.

    DEPRECATED: Use domain.get_persona() instead.

    Args:
        subdomain: The subdomain (recipes, inventory, shopping, etc.)
        step_type: The step type (read, write, generate, analyze).
    """
    return _get_domain().get_persona(subdomain, step_type)


def get_scope_for_subdomain(subdomain: str) -> str:
    """Get a formatted scope description for a subdomain."""
    scope = _get_subdomain_scope().get(subdomain, {})
    if not scope:
        return ""
    
    lines = []
    
    # Description
    if "description" in scope:
        lines.append(f"**Scope:** {scope['description']}")
    
    # Influenced by
    if "influenced_by" in scope:
        influenced = ", ".join(scope["influenced_by"])
        lines.append(f"**Influenced by:** {influenced}")
    
    # Implicit children
    if "implicit_children" in scope:
        children = ", ".join(scope["implicit_children"])
        lines.append(f"**Linked tables:** Always handle {children} together with this subdomain.")
    
    # Implicit dependencies
    if "implicit_dependencies" in scope:
        deps = ", ".join(scope["implicit_dependencies"])
        exceptions = scope.get("exception_meal_types", [])
        if exceptions:
            exc_str = ", ".join(exceptions)
            lines.append(f"**Dependencies:** Usually needs {deps} (except for {exc_str} meal types).")
        else:
            lines.append(f"**Dependencies:** Usually needs {deps}.")
    
    # Related
    if "related" in scope:
        related = ", ".join(scope["related"])
        lines.append(f"**Works with:** {related}")
    
    return "\n".join(lines)



# =============================================================================
# Schema Fetching
# =============================================================================


async def get_table_schema(table: str) -> dict[str, Any]:
    """
    Fetch column info for a table from Postgres information_schema.

    Uses an RPC function that must be created in the database:
    See migrations/004_schema_introspection.sql

    Args:
        table: Table name

    Returns:
        Dict with table name and column info
    """
    from alfred.domain import get_current_domain
    client = get_current_domain().get_db_adapter()

    try:
        result = client.rpc("get_table_columns", {"table_name": table}).execute()

        return {
            "table": table,
            "columns": [
                {
                    "name": col["column_name"],
                    "type": col["data_type"],
                    "nullable": col["is_nullable"] == "YES",
                }
                for col in result.data
            ],
        }
    except Exception as e:
        # Fallback: return empty schema if RPC not available
        # This allows development before migration is run
        return {
            "table": table,
            "columns": [],
            "error": str(e),
        }


async def get_subdomain_schema(subdomain: str) -> str:
    """
    Generate markdown schema for all tables in a subdomain.

    Args:
        subdomain: Subdomain name (e.g., "recipes", "inventory")

    Returns:
        Markdown-formatted schema for LLM consumption
    """
    tables = get_subdomain_tables(subdomain)

    if not tables:
        return f"Unknown subdomain: {subdomain}"

    schemas = []
    for table in tables:
        schema = await get_table_schema(table)
        schemas.append(schema)

    return format_as_markdown(schemas, subdomain)


# System columns to hide from LLM (auto-injected by CRUD tools)
HIDDEN_COLUMNS = {"user_id", "created_at", "updated_at"}


def format_as_markdown(schemas: list[dict], subdomain: str) -> str:
    """
    Convert schema dicts to readable markdown for LLM.

    Filters out system columns (user_id, created_at, updated_at) that
    are auto-injected by CRUD tools.

    Args:
        schemas: List of table schemas
        subdomain: Subdomain name for header

    Returns:
        Markdown string
    """
    lines = [f"## Available Tables (subdomain: {subdomain})", ""]

    for schema in schemas:
        table = schema["table"]
        columns = schema.get("columns", [])

        lines.append(f"### {table}")

        if not columns:
            if "error" in schema:
                lines.append(f"*Schema unavailable: {schema['error']}*")
            else:
                lines.append("*No columns found*")
            lines.append("")
            continue

        # Filter out hidden system columns
        visible_columns = [
            col for col in columns if col["name"] not in HIDDEN_COLUMNS
        ]

        lines.append("| Column | Type | Nullable |")
        lines.append("|--------|------|----------|")

        for col in visible_columns:
            nullable = "Yes" if col.get("nullable", True) else "No"
            lines.append(f"| {col['name']} | {col['type']} | {nullable} |")

        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Schema Cache
# =============================================================================


class SchemaCache:
    """
    Cache schemas per session to avoid repeated DB calls.

    Schemas rarely change, so we cache with a TTL.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[str, float]] = {}
        self._ttl = ttl_seconds

    async def get(self, subdomain: str) -> str:
        """
        Get schema for subdomain, using cache if valid.

        Args:
            subdomain: Subdomain name

        Returns:
            Markdown schema string
        """
        now = time.time()

        if subdomain in self._cache:
            schema, timestamp = self._cache[subdomain]
            if now - timestamp < self._ttl:
                return schema

        # Fetch fresh schema
        schema = await get_subdomain_schema(subdomain)
        self._cache[subdomain] = (schema, now)
        return schema

    def clear(self) -> None:
        """Clear the cache."""
        self._cache = {}

    def invalidate(self, subdomain: str) -> None:
        """Invalidate cache for a specific subdomain."""
        self._cache.pop(subdomain, None)


# Global cache instance
schema_cache = SchemaCache()


# =============================================================================
# Filter Schema + Field Enums
# =============================================================================

# Filter operators documentation
FILTER_SCHEMA = """## Filter Syntax

Structure: `{"field": "<column>", "op": "<operator>", "value": <value>}`

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Exact match | `{"field": "id", "op": "=", "value": "uuid"}` |
| `>` `<` `>=` `<=` | Comparison | `{"field": "quantity", "op": ">", "value": 5}` |
| `in` | Value in array | `{"field": "name", "op": "in", "value": ["milk", "eggs"]}` |
| `ilike` | Pattern match (% = wildcard) | `{"field": "name", "op": "ilike", "value": "%chicken%"}` |
| `is_null` | Null check | `{"field": "expiry_date", "op": "is_null", "value": true}` |
| `similar` | **Semantic search** (recipes only) | `{"field": "_semantic", "op": "similar", "value": "light summer dinner"}` |

### Semantic Search (`_semantic` filter)

For intent-based recipe queries, use the `_semantic` filter:
- **Good for**: "light summer dinner", "quick comfort food", "healthy breakfast", "something like pasta carbonara"
- **Combines with**: Other filters are applied AFTER semantic narrowing
- **Example**: Find light recipes with chicken:
  ```json
  {"filters": [
    {"field": "_semantic", "op": "similar", "value": "light healthy meal"},
    {"field": "name", "op": "ilike", "value": "%chicken%"}
  ]}
  ```

"""

# =============================================================================
# Kitchen Constants — Moved to alfred.domain.kitchen.schema (Phase 3a)
# Access via domain config methods or _get_* helpers below.
# =============================================================================


def _get_field_enums():
    """Get FIELD_ENUMS from domain config."""
    return _get_domain().get_field_enums()


def _get_semantic_notes():
    """Get SEMANTIC_NOTES from domain config."""
    return _get_domain().get_semantic_notes()


def _get_fallback_schemas():
    """Get FALLBACK_SCHEMAS from domain config."""
    return _get_domain().get_fallback_schemas()


def _get_subdomain_examples():
    """Get SUBDOMAIN_EXAMPLES from domain config."""
    return _get_domain().get_subdomain_examples()


# Legacy constant access — for imports like `from alfred.tools.schema import FIELD_ENUMS`
# These are consumed by web/schema_routes.py and tools/__init__.py. Redirect to domain.
def __getattr__(name):
    """Module-level __getattr__ for lazy constant access via domain config."""
    domain = _get_domain()
    _ATTR_MAP = {
        "FIELD_ENUMS": "get_field_enums",
        "SEMANTIC_NOTES": "get_semantic_notes",
        "FALLBACK_SCHEMAS": "get_fallback_schemas",
        "SUBDOMAIN_SCOPE": "get_subdomain_scope",
        "SUBDOMAIN_REGISTRY": "get_subdomain_registry",
        "SUBDOMAIN_EXAMPLES": "get_subdomain_examples",
    }
    if name in _ATTR_MAP:
        return getattr(domain, _ATTR_MAP[name])()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_subdomain_context(subdomain: str) -> str:
    """
    Get complete subdomain context for Act node:
    1. Filter schema (operators)
    2. Field enums (allowed values for categorical fields)
    3. Semantic notes (clarifications like "pantry = all inventory")
    4. CRUD examples
    """
    parts = [FILTER_SCHEMA]

    # Add field enums if available
    enums = _get_field_enums().get(subdomain, {})
    if enums:
        parts.append("## Field Values (Enums)\n")
        for field, values in enums.items():
            parts.append(f"- `{field}`: {', '.join(values)}")
        parts.append("")

    # Add semantic notes if available
    notes = _get_semantic_notes().get(subdomain, "")
    if notes.strip():
        parts.append(notes)

    # Add examples
    examples = _get_subdomain_examples().get(subdomain, "")
    if examples:
        parts.append(examples)

    return "\n".join(parts)


async def get_schema_with_fallback(subdomain: str) -> str:
    """
    Get schema for subdomain, falling back to hardcoded if DB unavailable.
    
    Includes:
    - Table column definitions (schema)
    - Subdomain-specific CRUD examples with exact filter syntax

    Args:
        subdomain: Subdomain name

    Returns:
        Markdown schema string + CRUD examples
    """
    fallback_schemas = _get_fallback_schemas()
    try:
        schema = await schema_cache.get(subdomain)
        # If schema is empty or has errors, use fallback
        if "No columns found" in schema or "Schema unavailable" in schema:
            schema = fallback_schemas.get(subdomain, schema)
    except Exception:
        schema = fallback_schemas.get(
            subdomain, f"Unknown subdomain: {subdomain}"
        )
    
    # Append subdomain context (filter schema + enums + notes + examples)
    context = get_subdomain_context(subdomain)
    if context:
        return f"{schema}\n{context}"
    return schema


# =============================================================================
# Schema Drift Validation
# =============================================================================


async def validate_schema_drift() -> list[str]:
    """
    Compare FALLBACK_SCHEMAS to actual DB schema and report drift.
    
    Call this on startup to catch schema mismatches early.
    
    Returns:
        List of warning messages (empty if no drift)
    """
    warnings = []
    registry = _get_subdomain_registry()
    fallback_schemas = _get_fallback_schemas()

    for subdomain in registry:
        tables = get_subdomain_tables(subdomain)
        for table in tables:
            try:
                db_schema = await get_table_schema(table)
                db_columns = {col["name"] for col in db_schema.get("columns", [])}

                if not db_columns:
                    warnings.append(f"⚠️ Table '{table}' not found in database")
                    continue

                # Parse fallback schema for this subdomain
                fallback = fallback_schemas.get(subdomain, "")
                if f"### {table}" in fallback:
                    # Extract column names from markdown table
                    import re
                    pattern = rf"### {table}\n.*?\n\|.*?\n\|.*?\n((?:\|.*?\n)+)"
                    match = re.search(pattern, fallback, re.DOTALL)
                    if match:
                        lines = match.group(1).strip().split("\n")
                        fallback_columns = set()
                        for line in lines:
                            parts = line.split("|")
                            if len(parts) >= 2:
                                col_name = parts[1].strip()
                                if col_name and col_name not in ("Column", "---"):
                                    fallback_columns.add(col_name)
                        
                        # Compare (ignore hidden columns)
                        fallback_visible = fallback_columns - HIDDEN_COLUMNS
                        db_visible = db_columns - HIDDEN_COLUMNS
                        
                        missing_in_db = fallback_visible - db_visible
                        missing_in_fallback = db_visible - fallback_visible
                        
                        if missing_in_db:
                            warnings.append(
                                f"⚠️ {subdomain}.{table}: Columns in fallback but not DB: {missing_in_db}"
                            )
                        if missing_in_fallback:
                            warnings.append(
                                f"ℹ️ {subdomain}.{table}: Columns in DB but not fallback: {missing_in_fallback}"
                            )
            except Exception as e:
                warnings.append(f"❌ Error checking {subdomain}.{table}: {e}")
    
    return warnings


async def log_schema_drift_warnings():
    """Log schema drift warnings on startup."""
    import logging
    logger = logging.getLogger(__name__)
    
    warnings = await validate_schema_drift()
    if warnings:
        logger.warning("Schema drift detected:")
        for w in warnings:
            logger.warning(f"  {w}")
    else:
        logger.info("Schema validation passed - no drift detected")

