"""Application configuration.

All settings are overridable via ``ARC_EVAL_*`` environment variables. The
instance is frozen and cached so it can be shared safely and used as an
``lru_cache`` key elsewhere.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from arc_eval_service.models.profiles import ModelProfile


class Settings(BaseSettings):
    """Runtime settings for arc-eval-service."""

    # protected_namespaces=() so model-related fields (model_profiles,
    # default_model) don't collide with pydantic's reserved ``model_`` namespace.
    model_config = SettingsConfigDict(
        env_prefix="ARC_EVAL_", frozen=True, protected_namespaces=()
    )

    app_name: str = "arc-eval-service"
    service_name: str = "arc-eval-service"
    log_level: str = "INFO"

    # Upper bound on a single batch request, guarding the store.
    max_batch_size: int = 100

    # When set, the service persists to Postgres; otherwise it uses the in-memory
    # store. Use the psycopg3 driver, e.g.
    #   postgresql+psycopg://user:pass@host:5432/arc_eval
    database_url: str | None = None

    # --- judge models (BYOK) ---------------------------------------------
    # JSON list of server-side model profiles; the API key is referenced by env
    # var name (api_key_env), never stored here. Example:
    #   ARC_EVAL_MODEL_PROFILES='[{"name":"default","provider":"anthropic",
    #     "model":"claude-opus-4-8","api_key_env":"ANTHROPIC_API_KEY"}]'
    model_profiles: list[ModelProfile] = []
    default_model: str | None = None  # profile name used when a request omits one
    default_judge: str = "safety"  # judge used for offline (OTel) ingestion

    # --- offline (OTel) ingestion ----------------------------------------
    ingest_enabled: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
