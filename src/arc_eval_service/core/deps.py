"""Dependency injection wiring.

The api/ layer depends on these factories rather than constructing the store,
registry or service directly. This keeps layering (api -> services -> storage)
one-directional and the persistence backend swappable behind ``get_store``.
"""

from __future__ import annotations

from functools import lru_cache

from arc_eval_service.core.config import get_settings
from arc_eval_service.evaluators.registry import EvaluatorRegistry, default_registry
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.storage.base import EvaluationStore
from arc_eval_service.storage.memory import InMemoryEvaluationStore
from arc_eval_service.storage.postgres import PostgresEvaluationStore


@lru_cache(maxsize=1)
def get_store() -> EvaluationStore:
    """Return the process-wide evaluation store.

    Uses Postgres when ``ARC_EVAL_DATABASE_URL`` is configured, otherwise falls
    back to the in-memory store (default for local dev and tests).
    """
    settings = get_settings()
    if settings.database_url:
        return PostgresEvaluationStore(settings.database_url)
    return InMemoryEvaluationStore()


@lru_cache(maxsize=1)
def get_registry() -> EvaluatorRegistry:
    """Return the process-wide evaluator registry."""
    return default_registry()


def get_evaluation_service() -> EvaluationService:
    """Return an :class:`EvaluationService` wired to the active store + registry."""
    return EvaluationService(store=get_store(), registry=get_registry())
