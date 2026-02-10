"""
Session management helpers for Alfred.

Handles session timeout logic and metadata for conversation state.
Database persistence for conversations (survives deployments/restarts).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from alfred_kitchen.config import get_settings
from alfred_kitchen.db.client import get_authenticated_client
from alfred.memory.conversation import initialize_conversation

logger = logging.getLogger(__name__)


SessionStatus = Literal["active", "stale", "none"]


class SessionPreview(TypedDict):
    last_message: str
    message_count: int


class SessionStatusResponse(TypedDict):
    status: SessionStatus
    last_active_at: str | None
    preview: SessionPreview | None


def _utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def _parse_iso(iso_str: str | None) -> datetime | None:
    """Parse ISO format string to datetime."""
    if not iso_str:
        return None
    try:
        # Handle both with and without timezone
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


def _ensure_metadata(conv_state: dict[str, Any]) -> dict[str, Any]:
    """Backfill session metadata for legacy conversations.

    Adds created_at and last_active_at if missing.
    Private helper used on read paths only (load from DB, get from cache).
    Returns the same dict (mutated) for convenience.
    """
    now = _utc_now().isoformat()
    if "created_at" not in conv_state:
        conv_state["created_at"] = now
    if "last_active_at" not in conv_state:
        conv_state["last_active_at"] = now
    return conv_state


def create_fresh_session() -> dict[str, Any]:
    """Create a new conversation with session metadata initialized."""
    conv = initialize_conversation()
    now = _utc_now().isoformat()
    conv["created_at"] = now
    conv["last_active_at"] = now
    return conv


def get_session_status(conv_state: dict[str, Any] | None) -> SessionStatusResponse:
    """Check session status based on timestamps.

    Returns:
        - "none": No session exists
        - "active": Within active timeout (30 min default)
        - "stale": Beyond active timeout but not expired (show resume prompt)

    Sessions beyond expire_hours (24h default) are auto-cleared before this is called.
    """
    if not conv_state:
        return {
            "status": "none",
            "last_active_at": None,
            "preview": None,
        }

    settings = get_settings()
    active_timeout_minutes = settings.session_active_timeout_minutes

    last_active_str = conv_state.get("last_active_at")
    last_active = _parse_iso(last_active_str)

    # No timestamp = treat as fresh (backward compatibility)
    if not last_active:
        return {
            "status": "active",
            "last_active_at": None,
            "preview": None,
        }

    now = _utc_now()
    minutes_since_active = (now - last_active).total_seconds() / 60

    # Build preview from recent_turns
    preview = None
    recent_turns = conv_state.get("recent_turns", [])
    if recent_turns:
        last_turn = recent_turns[-1]
        # Prefer assistant response, fall back to user message
        last_msg = last_turn.get("assistant", last_turn.get("user", ""))
        if isinstance(last_msg, dict):
            # Handle structured response format
            last_msg = last_msg.get("text", str(last_msg))
        last_msg = str(last_msg)
        preview = {
            "last_message": last_msg[:50] + "..." if len(last_msg) > 50 else last_msg,
            "message_count": len(recent_turns),
        }

    status: SessionStatus = "active" if minutes_since_active <= active_timeout_minutes else "stale"

    return {
        "status": status,
        "last_active_at": last_active_str,
        "preview": preview,
    }


def is_session_expired(conv_state: dict[str, Any] | None) -> bool:
    """Check if session is beyond the expiration threshold (24h default).

    Expired sessions should be cleared.
    """
    if not conv_state:
        return False

    settings = get_settings()
    expire_hours = settings.session_expire_hours

    last_active = _parse_iso(conv_state.get("last_active_at"))
    if not last_active:
        # No timestamp = don't expire (backward compatibility)
        return False

    now = _utc_now()
    hours_since_active = (now - last_active).total_seconds() / 3600

    return hours_since_active > expire_hours


# =============================================================================
# Database Persistence
# =============================================================================


def load_conversation_from_db(access_token: str, user_id: str) -> dict[str, Any] | None:
    """Load conversation state from database.

    Args:
        access_token: User's JWT for authenticated DB access
        user_id: User's UUID

    Returns:
        Conversation state dict, or None if not found
    """
    try:
        client = get_authenticated_client(access_token)
        result = (
            client.table("conversations")
            .select("state, created_at, last_active_at")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        # Handle case where result is None (RLS or client error)
        if result is None:
            return None

        if result.data:
            conv = result.data.get("state") or {}
            # Merge DB columns into state dict (timestamps are separate columns)
            if result.data.get("created_at"):
                conv["created_at"] = result.data["created_at"]
            if result.data.get("last_active_at"):
                conv["last_active_at"] = result.data["last_active_at"]
            _ensure_metadata(conv)
            return conv

        return None

    except Exception as e:
        logger.warning(f"Failed to load conversation from DB for user {user_id}: {e}")
        return None


def commit_conversation(
    user_id: str,
    access_token: str,
    conv_state: dict[str, Any],
    cache: dict[str, dict[str, Any]],
) -> None:
    """Single point of mutation for all conversation state updates.

    Handles: timestamp stamping + memory cache + DB persistence.
    Every code path that changes conversation state MUST call this.
    No other code should directly write to cache or call _save_to_db.
    """
    now = _utc_now().isoformat()
    conv_state["last_active_at"] = now
    if "created_at" not in conv_state:
        conv_state["created_at"] = now

    cache[user_id] = conv_state
    _save_to_db(access_token, user_id, conv_state)


def _save_to_db(access_token: str, user_id: str, conv_state: dict[str, Any]) -> bool:
    """Save conversation state to database (upsert). Private - use commit_conversation().

    Args:
        access_token: User's JWT for authenticated DB access
        user_id: User's UUID
        conv_state: Full conversation state dict

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        client = get_authenticated_client(access_token)

        # Upsert: insert or update on conflict
        client.table("conversations").upsert(
            {
                "user_id": user_id,
                "state": conv_state,
                "last_active_at": _utc_now().isoformat(),
            },
            on_conflict="user_id",
        ).execute()

        return True

    except Exception as e:
        logger.error(f"Failed to save conversation to DB for user {user_id}: {e}")
        return False


def delete_conversation_from_db(access_token: str, user_id: str) -> bool:
    """Delete conversation from database (for reset).

    Args:
        access_token: User's JWT for authenticated DB access
        user_id: User's UUID

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        client = get_authenticated_client(access_token)
        client.table("conversations").delete().eq("user_id", user_id).execute()
        return True

    except Exception as e:
        logger.warning(f"Failed to delete conversation from DB for user {user_id}: {e}")
        return False
