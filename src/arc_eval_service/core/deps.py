"""Dependency injection wiring.

The api/ layer depends on these factories rather than constructing the store,
registries or service directly. This keeps layering (api -> services ->
{judges, models, storage}) one-directional and every collaborator swappable.
"""

from __future__ import annotations

from functools import lru_cache

from arc_eval_service.core.config import get_settings
from arc_eval_service.ingest import OfflineIngestService
from arc_eval_service.judges.registry import JudgeRegistry, default_registry
from arc_eval_service.models.profiles import ModelRegistry
from arc_eval_service.services.discovery import DiscoveryService
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.services.traces import TraceService
from arc_eval_service.storage.evaluation import (
    EvaluationStore,
    InMemoryEvaluationStore,
    PostgresEvaluationStore,
)
from arc_eval_service.storage.spans import (
    InMemorySpanStore,
    PostgresSpanStore,
    SpanStore,
)


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
def get_span_store() -> SpanStore:
    """Return the process-wide span (trace) store.

    Mirrors :func:`get_store`: Postgres when configured, in-memory otherwise.
    """
    settings = get_settings()
    if settings.database_url:
        return PostgresSpanStore(settings.database_url)
    return InMemorySpanStore()


@lru_cache(maxsize=1)
def get_judges() -> JudgeRegistry:
    """Return the process-wide judge registry."""
    return default_registry()


@lru_cache(maxsize=1)
def get_models() -> ModelRegistry:
    """Return the process-wide model registry built from configured profiles."""
    settings = get_settings()
    return ModelRegistry(settings.model_profiles, default=settings.default_model)


def get_evaluation_service() -> EvaluationService:
    """Return an :class:`EvaluationService` wired to its collaborators."""
    return EvaluationService(
        store=get_store(), judges=get_judges(), models=get_models()
    )


def get_discovery_service() -> DiscoveryService:
    """Return a :class:`DiscoveryService` over the judge + model registries."""
    return DiscoveryService(judges=get_judges(), models=get_models())


def get_trace_service() -> TraceService:
    """Return a :class:`TraceService` wired to the span store."""
    return TraceService(spans=get_span_store())


def get_offline_ingest_service() -> OfflineIngestService:
    """Return the OTel offline-ingestion service (gateway -> collector -> here)."""
    settings = get_settings()
    return OfflineIngestService(
        evaluation=get_evaluation_service(),
        spans=get_span_store(),
        self_service_name=settings.service_name,
        default_judge=settings.default_judge,
        default_model=settings.default_model,
    )
