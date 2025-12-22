"""
Alfred V2 - Database Client.

Provides Supabase access with hybrid SQL + vector retrieval.
"""

from alfred.db.client import get_client
from alfred.db.context import get_context

__all__ = [
    "get_client",
    "get_context",
]
