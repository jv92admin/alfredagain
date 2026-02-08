"""
Alfred V2 - Background Jobs Package.

Provides async/background processing for:
- Profile building and caching
- Kitchen dashboard for Think node
- Aggregation of cooking history
- Pre-computation of user signals
"""

from alfred_kitchen.background.profile_builder import (
    KitchenDashboard,
    UserProfile,
    build_kitchen_dashboard,
    build_user_profile,
    format_dashboard_for_prompt,
    format_profile_for_prompt,
    get_cached_dashboard,
    get_cached_profile,
    invalidate_dashboard_cache,
    invalidate_profile_cache,
)

__all__ = [
    "KitchenDashboard",
    "UserProfile",
    "build_kitchen_dashboard",
    "build_user_profile",
    "format_dashboard_for_prompt",
    "format_profile_for_prompt",
    "get_cached_dashboard",
    "get_cached_profile",
    "invalidate_dashboard_cache",
    "invalidate_profile_cache",
]

