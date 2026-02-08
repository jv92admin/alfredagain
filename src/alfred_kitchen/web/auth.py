"""
Authentication utilities for FastAPI routes.

Shared auth dependency used by all route modules.
"""

import logging

from fastapi import HTTPException, Header
from pydantic import BaseModel

from alfred_kitchen.db.client import get_service_client

logger = logging.getLogger(__name__)


class AuthenticatedUser(BaseModel):
    """Authenticated user info from Supabase JWT."""
    id: str
    email: str | None
    access_token: str


async def get_current_user(authorization: str = Header(None)) -> AuthenticatedUser:
    """
    Validate Supabase JWT and extract user info.

    Expects Authorization header: "Bearer <access_token>"
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    access_token = authorization[7:]  # Remove "Bearer " prefix

    try:
        # Use service client to validate the token
        client = get_service_client()
        user_response = client.auth.get_user(access_token)

        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user = user_response.user
        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            access_token=access_token
        )
    except Exception as e:
        logger.warning(f"Auth validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
