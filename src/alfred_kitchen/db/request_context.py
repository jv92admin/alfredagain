"""
Alfred - Request Context for Authentication.

Uses context variables to pass the authenticated user's access token
through the request without threading it through every function.
"""

from contextvars import ContextVar
from typing import Optional

# Context variable for the current request's access token
_access_token: ContextVar[Optional[str]] = ContextVar("access_token", default=None)
_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def set_request_context(access_token: str | None = None, user_id: str | None = None):
    """
    Set the authentication context for the current request.
    
    Call this at the start of request handling (before running Alfred).
    """
    if access_token:
        _access_token.set(access_token)
    if user_id:
        _user_id.set(user_id)


def get_access_token() -> str | None:
    """Get the current request's access token."""
    return _access_token.get()


def get_current_user_id() -> str | None:
    """Get the current request's user ID."""
    return _user_id.get()


def clear_request_context():
    """Clear the request context (call at end of request)."""
    _access_token.set(None)
    _user_id.set(None)
