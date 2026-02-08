"""
Alfred Core - Configuration and settings.

CoreSettings contains only what the orchestration engine needs.
Domain-specific settings live in domain packages (e.g., alfred_kitchen.config).
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """
    Core settings shared by all domains.

    Contains only what the alfred orchestration engine needs.
    Domain-specific settings (Supabase, session, etc.) go in subclasses.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str

    # LangSmith (optional)
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "alfred-v2"

    # Application
    alfred_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Prompt logging
    # ALFRED_LOG_PROMPTS=1 - log to local files (dev only)
    alfred_log_prompts: bool = False

    @property
    def is_development(self) -> bool:
        return self.alfred_env == "development"

    @property
    def is_production(self) -> bool:
        return self.alfred_env == "production"


@lru_cache
def get_core_settings() -> CoreSettings:
    """Get cached CoreSettings instance (no Supabase fields required)."""
    return CoreSettings()


class _CoreSettingsProxy:
    """Lazy proxy for CoreSettings — only needs OPENAI_API_KEY."""

    _instance: CoreSettings | None = None

    def __getattr__(self, name: str):
        if self._instance is None:
            self._instance = get_core_settings()
        return getattr(self._instance, name)


core_settings = _CoreSettingsProxy()


# ---------------------------------------------------------------------------
# Backwards-compat: Settings, get_settings, settings proxy
#
# These exist so existing code doing `from alfred.config import settings`
# continues to work. They instantiate KitchenSettings (the full Settings
# class that includes Supabase fields) via lazy import.
#
# New core code should only depend on CoreSettings fields.
# ---------------------------------------------------------------------------

# Re-export Settings from kitchen for backwards compat
def __getattr__(name: str):
    if name == "Settings":
        from alfred_kitchen.config import KitchenSettings
        return KitchenSettings
    if name == "get_settings":
        from alfred_kitchen.config import get_settings
        return get_settings
    if name == "settings":
        from alfred_kitchen.config import settings
        return settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
