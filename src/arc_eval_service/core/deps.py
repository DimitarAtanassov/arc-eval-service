"""Dependency injection wiring (composition root).

Routes depend on these factories rather than constructing the database or
services directly, keeping every collaborator swappable in tests. The database is
a process-wide singleton; repositories and services are cheap per-request
wrappers over its session factory.
"""

from __future__ import annotations

from functools import lru_cache

from arc_eval_service.core.config import get_settings
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import (
    EvalInputRepository,
    PromptTemplateRepository,
)
from arc_eval_service.ingestion.service import IngestionService


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Return the process-wide database (engine + session factory)."""
    url = get_settings().database_url
    if url is None:
        msg = "ARC_EVAL_DATABASE_URL must be set"
        raise RuntimeError(msg)
    return Database(url)


def get_prompt_template_repository() -> PromptTemplateRepository:
    return PromptTemplateRepository(get_database().sessionmaker)


def get_eval_input_repository() -> EvalInputRepository:
    return EvalInputRepository(get_database().sessionmaker)


def get_ingestion_service() -> IngestionService:
    """Return an :class:`IngestionService` wired to its repositories."""
    return IngestionService(
        templates=get_prompt_template_repository(),
        inputs=get_eval_input_repository(),
    )
