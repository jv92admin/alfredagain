"""
Database Adapter Protocol.

Defines the abstract interface for database access in Alfred's core.
Domains provide implementations (e.g., Supabase, SQLite) via
DomainConfig.get_db_adapter().

The adapter exposes a thin wrapper matching the Supabase/PostgREST
query builder pattern: table() returns a query builder, rpc() calls
stored procedures. Core's CRUD executor uses these methods directly.

Conscious deferral: apply_filter() in tools/crud.py is coupled to the
PostgREST query builder interface (.eq(), .gt(), .ilike(), etc. — 12
methods). This is acceptable while all domains use Supabase. If a
future domain uses a different DB, apply_filter() becomes the
refactor point.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseAdapter(Protocol):
    """
    Abstract database access for Alfred's CRUD layer.

    Implementations wrap a database client (e.g., Supabase) and expose
    the query builder pattern used by tools/crud.py.

    The table() method returns a query builder — the concrete type
    depends on the database backend (e.g., SyncSelectRequestBuilder
    for Supabase). Core builds queries fluently on the returned builder.

    The rpc() method calls stored procedures / database functions.
    """

    def table(self, name: str) -> Any:
        """
        Return a query builder for the given table.

        The returned object must support the PostgREST-style fluent API:
        .select(), .insert(), .update(), .delete(), .eq(), .execute(), etc.
        """
        ...

    def rpc(self, function_name: str, params: dict) -> Any:
        """
        Call a stored procedure / database function.

        Returns an object with .execute() that yields .data.
        """
        ...
