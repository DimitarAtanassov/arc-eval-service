"""Dependency injection wiring (composition root).

Routers depend on these factories rather than constructing the database,
registries or services directly, keeping every collaborator swappable. The
database engine and the registries are process-wide singletons; repositories and
services are cheap per-request wrappers over them.
"""

from __future__ import annotations

from functools import lru_cache

from arc_eval_service.core.config import get_settings
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import (
    CaseRepository,
    ResultRepository,
    TraceRepository,
)
from arc_eval_service.discovery.service import DiscoveryService
from arc_eval_service.evaluation.service import EvaluationService
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.metrics.registry import MetricRegistry, default_registry
from arc_eval_service.traces.ingest import IngestService
from arc_eval_service.traces.service import TraceService


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Return the process-wide database (engine + session factory)."""
    return Database(get_settings().database_url)


@lru_cache(maxsize=1)
def get_metric_registry() -> MetricRegistry:
    """Return the process-wide metric registry."""
    return default_registry()


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """Return the process-wide model registry built from configured profiles."""
    settings = get_settings()
    return ModelRegistry(settings.model_profiles, default=settings.default_model)


def get_case_repository() -> CaseRepository:
    return CaseRepository(get_database().sessionmaker)


def get_result_repository() -> ResultRepository:
    return ResultRepository(get_database().sessionmaker)


def get_trace_repository() -> TraceRepository:
    return TraceRepository(get_database().sessionmaker)


def get_evaluation_service() -> EvaluationService:
    """Return an :class:`EvaluationService` wired to its collaborators."""
    return EvaluationService(
        cases=get_case_repository(),
        results=get_result_repository(),
        metrics=get_metric_registry(),
        models=get_model_registry(),
    )


def get_discovery_service() -> DiscoveryService:
    """Return a :class:`DiscoveryService` over the metric + model registries."""
    return DiscoveryService(metrics=get_metric_registry(), models=get_model_registry())


def get_trace_service() -> TraceService:
    """Return a :class:`TraceService` wired to the trace store."""
    return TraceService(get_trace_repository())


def get_ingest_service() -> IngestService:
    """Return the OTel offline-ingestion service (gateway -> collector -> here)."""
    settings = get_settings()
    return IngestService(
        evaluation=get_evaluation_service(),
        traces=get_trace_repository(),
        self_service_name=settings.service_name,
        default_metric=settings.default_metric,
        default_model=settings.default_model,
    )
