"""
Alfred V2 - Background Jobs Package.

Provides async/background processing for:
- Profile building and caching
- Aggregation of cooking history
- Pre-computation of user signals
"""

from alfred.background.profile_builder import (
    UserProfile,
    build_user_profile,
    format_profile_for_prompt,
)

__all__ = [
    "UserProfile",
    "build_user_profile",
    "format_profile_for_prompt",
]

