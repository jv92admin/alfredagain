"""
Alfred V2 - Tools Package.

Provides generic CRUD tools and schema generation.

Tools:
- db_read: Fetch rows with filters
- db_create: Insert new records  
- db_update: Update existing records
- db_delete: Delete records

Schema:
- SUBDOMAIN_REGISTRY: Maps subdomains to tables
- get_schema_with_fallback: Get schema for a subdomain
"""

from alfred.tools.crud import (
    DbCreateParams,
    DbDeleteParams,
    DbReadParams,
    DbUpdateParams,
    FilterClause,
    db_create,
    db_delete,
    db_read,
    db_update,
    execute_crud,
)
from alfred.tools.schema import (
    SUBDOMAIN_REGISTRY,
    get_schema_with_fallback,
    schema_cache,
)

__all__ = [
    # CRUD tools
    "db_read",
    "db_create",
    "db_update",
    "db_delete",
    "execute_crud",
    # Parameter models
    "DbReadParams",
    "DbCreateParams",
    "DbUpdateParams",
    "DbDeleteParams",
    "FilterClause",
    # Schema
    "SUBDOMAIN_REGISTRY",
    "get_schema_with_fallback",
    "schema_cache",
]
