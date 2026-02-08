"""
Alfred - Database Layer.

Provides the DatabaseAdapter protocol for domain-agnostic DB access.
For the Supabase client, import from alfred_kitchen.db.client.
"""

from alfred.db.adapter import DatabaseAdapter

__all__ = [
    "DatabaseAdapter",
]


def __getattr__(name: str):
    """Backwards-compat: redirect get_client to alfred_kitchen."""
    if name == "get_client":
        from alfred_kitchen.db.client import get_client
        return get_client
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
