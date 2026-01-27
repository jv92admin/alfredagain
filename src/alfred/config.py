"""
Alfred V2 - Configuration and settings.

Uses pydantic-settings for type-safe environment variable loading.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # LangSmith (optional)
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "alfred-v2"

    # Application
    alfred_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    # Prompt logging
    # ALFRED_LOG_PROMPTS=1 - log to local files (dev only)
    # ALFRED_LOG_TO_DB=1 - log to Supabase prompt_logs table (works in production)
    alfred_log_prompts: bool = False
    alfred_log_to_db: bool = False
    alfred_log_keep_sessions: int = 4  # Keep last N sessions in DB
    
    # Dev user - matches the user created in migrations/001_core_tables.sql
    # Skip auth for now, use this hardcoded user
    dev_user_id: str = "00000000-0000-0000-0000-000000000002"  # Alice

    # Session management
    session_active_timeout_minutes: int = 30  # Prompt to resume after this
    session_expire_hours: int = 24  # Auto-clear session after this

    @property
    def is_development(self) -> bool:
        return self.alfred_env == "development"
    
    @property
    def is_production(self) -> bool:
        return self.alfred_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience singleton - lazy loaded
class _SettingsProxy:
    """Lazy proxy for settings to avoid loading .env at import time."""
    
    _instance: Settings | None = None
    
    def __getattr__(self, name: str):
        if self._instance is None:
            self._instance = get_settings()
        return getattr(self._instance, name)


settings = _SettingsProxy()

