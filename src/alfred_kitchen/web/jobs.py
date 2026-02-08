"""
Job lifecycle management for Alfred.

Tracks chat request lifecycle (pending → running → complete → failed) so
responses survive client disconnects. Single-owner module — all job mutations
go through functions in this file.

See: docs/ideas/job-durability-spec.md (Phase 2.5)
"""

import logging
from datetime import UTC, datetime
from typing import Any

from alfred_kitchen.db.client import get_authenticated_client

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(UTC).isoformat()


def create_job(access_token: str, user_id: str, input_data: dict[str, Any]) -> str | None:
    """Create a pending job. Returns job_id or None on failure."""
    try:
        client = get_authenticated_client(access_token)
        result = (
            client.table("jobs")
            .insert(
                {
                    "user_id": user_id,
                    "status": "pending",
                    "input": input_data,
                }
            )
            .execute()
        )
        if result.data and len(result.data) > 0:
            return result.data[0]["id"]
        return None
    except Exception as e:
        logger.error(f"Failed to create job for user {user_id}: {e}")
        return None


def start_job(access_token: str, job_id: str) -> None:
    """Mark job as running with started_at timestamp."""
    try:
        client = get_authenticated_client(access_token)
        client.table("jobs").update(
            {
                "status": "running",
                "started_at": _utc_now(),
            }
        ).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"Failed to start job {job_id}: {e}")


def complete_job(access_token: str, job_id: str, output: dict[str, Any]) -> None:
    """Mark job as complete with response and completed_at timestamp."""
    try:
        client = get_authenticated_client(access_token)
        client.table("jobs").update(
            {
                "status": "complete",
                "output": output,
                "completed_at": _utc_now(),
            }
        ).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"Failed to complete job {job_id}: {e}")


def fail_job(access_token: str, job_id: str, error: str) -> None:
    """Mark job as failed with error message and completed_at timestamp."""
    try:
        client = get_authenticated_client(access_token)
        client.table("jobs").update(
            {
                "status": "failed",
                "error": error,
                "completed_at": _utc_now(),
            }
        ).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"Failed to mark job {job_id} as failed: {e}")


def acknowledge_job(access_token: str, job_id: str) -> None:
    """Mark job as acknowledged (client received the response)."""
    try:
        client = get_authenticated_client(access_token)
        client.table("jobs").update(
            {
                "acknowledged_at": _utc_now(),
            }
        ).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"Failed to acknowledge job {job_id}: {e}")


def get_job(access_token: str, job_id: str) -> dict[str, Any] | None:
    """Get job by ID."""
    try:
        client = get_authenticated_client(access_token)
        result = (
            client.table("jobs")
            .select("*")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if result is None:
            return None
        return result.data
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        return None


def get_active_job(access_token: str, user_id: str) -> dict[str, Any] | None:
    """Get the user's most recent unacknowledged running/complete job.

    Returns None if no active job exists. Used by frontend on reconnect
    to recover missed responses.
    """
    try:
        client = get_authenticated_client(access_token)
        result = (
            client.table("jobs")
            .select("*")
            .eq("user_id", user_id)
            .is_("acknowledged_at", "null")
            .in_("status", ["running", "complete"])
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if result is None:
            return None
        return result.data
    except Exception as e:
        logger.error(f"Failed to get active job for user {user_id}: {e}")
        return None
