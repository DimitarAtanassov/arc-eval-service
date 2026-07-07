"""Dependency injection wiring (composition root).

Routes depend on these factories rather than constructing the database, engine or
services directly, keeping every collaborator swappable in tests (via FastAPI
``dependency_overrides``). The database is a process-wide singleton because it owns
the connection pool; everything else is a cheap per-request wrapper over it.
"""

from __future__ import annotations

from functools import lru_cache

from arc_eval_service.catalog import Catalog, load_catalog
from arc_eval_service.core.config import get_settings
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.services.evaluation_service import EvaluationService
from arc_eval_service.services.read_service import ReadService


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Return the process-wide database (engine + session factory)."""
    url = get_settings().database_url
    if url is None:
        msg = "ARC_EVAL_DATABASE_URL must be set"
        raise RuntimeError(msg)
    return Database(url)


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Return the process-wide prompt library (loaded and validated once)."""
    return load_catalog(get_settings().prompts_path)


def get_model_registry() -> ModelRegistry:
    """Return the judge-model registry built from configured profiles."""
    settings = get_settings()
    return ModelRegistry(settings.model_profiles, default=settings.default_model)


def get_judge_engine() -> JudgeEngine:
    """Return a :class:`JudgeEngine` over the prompt library and model registry."""
    return JudgeEngine(
        library=get_catalog(),
        models=get_model_registry(),
        default_judge=get_settings().default_judge,
    )


def get_evaluation_service() -> EvaluationService:
    """Return an :class:`EvaluationService` wired to the engine and repositories."""
    database = get_database()
    return EvaluationService(
        engine=get_judge_engine(),
        library=get_catalog(),
        requests=EvalRequestRepository(database.sessionmaker),
        results=EvaluationResultRepository(database.sessionmaker),
    )


def get_read_service() -> ReadService:
    """Return a :class:`ReadService` for the browse endpoints (reads only)."""
    database = get_database()
    return ReadService(
        requests=EvalRequestRepository(database.sessionmaker),
        results=EvaluationResultRepository(database.sessionmaker),
        catalog=get_catalog(),
    )
