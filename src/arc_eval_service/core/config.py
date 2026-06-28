"""Application configuration.

All settings are overridable via ``ARC_EVAL_*`` environment variables. The
instance is frozen and cached so it can be shared safely and used as an
``lru_cache`` key elsewhere.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for arc-eval-service."""

    model_config = SettingsConfigDict(env_prefix="ARC_EVAL_", frozen=True)

    app_name: str = "arc-eval-service"
    service_name: str = "arc-eval-service"
    log_level: str = "INFO"

    # Upper bound on a single batch request, guarding the store.
    max_batch_size: int = 100

    # When set, the service persists to Postgres; otherwise it uses the in-memory
    # store. Use the psycopg3 driver, e.g.
    #   postgresql+psycopg://user:pass@host:5432/arc_eval
    database_url: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
