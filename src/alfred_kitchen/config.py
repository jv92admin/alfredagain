"""
Alfred Kitchen - Configuration and settings.

KitchenSettings extends CoreSettings with Supabase and kitchen-specific fields.
"""

from functools import lru_cache

from alfred.config import CoreSettings


class KitchenSettings(CoreSettings):
    """
    Kitchen application settings.

    Extends CoreSettings with Supabase, session management, and
    kitchen-specific configuration.
    """

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # DB prompt logging (requires Supabase)
    alfred_log_to_db: bool = False
    alfred_log_keep_sessions: int = 4  # Keep last N sessions in DB

    # Dev user - matches the user created in migrations/001_core_tables.sql
    dev_user_id: str = "00000000-0000-0000-0000-000000000002"  # Alice

    # Session management
    session_active_timeout_minutes: int = 30  # Prompt to resume after this
    session_expire_hours: int = 24  # Auto-clear session after this


# Backwards compat alias
Settings = KitchenSettings


@lru_cache
def get_settings() -> KitchenSettings:
    """Get cached settings instance."""
    return KitchenSettings()


# Convenience singleton - lazy loaded
class _SettingsProxy:
    """Lazy proxy for settings to avoid loading .env at import time."""

    _instance: KitchenSettings | None = None

    def __getattr__(self, name: str):
        if self._instance is None:
            self._instance = get_settings()
        return getattr(self._instance, name)


settings = _SettingsProxy()
