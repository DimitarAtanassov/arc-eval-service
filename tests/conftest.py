"""Shared test fixtures.

A session-scoped Postgres testcontainer backs every DB-touching test; pure-logic
unit tests need none of it (heavy imports are deferred into the DB fixtures). The
``client`` fixture overrides the model registry with a stub so no judge call hits
the network -- metrics and orchestration run for real, the model is faked.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from arc_eval_service.core.errors import ModelError, UnknownModelError
from arc_eval_service.judging.model import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry

GOOD_VERDICT = '{"score": 0.9, "label": "pass", "explanation": "looks good"}'
_TABLES = ("eval_results", "cases", "spans", "traces")


class StubModel(JudgeModel):
    """A judge model that returns canned text (or fails) without any network."""

    provider = "stub"

    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.name = "stub-model"
        self._text = text
        self._fail = fail

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        if self._fail:
            raise ModelError("stub model failure")
        return ModelCompletion(text=self._text, model=self.name)


class StubModelRegistry(ModelRegistry):
    """A registry with one ``default`` profile that resolves to a stub model."""

    def __init__(self, *, text: str = GOOD_VERDICT, fail: bool = False) -> None:
        super().__init__(
            [ModelProfile(name="default", provider="openai_compatible", model="stub")],
            default="default",
        )
        self._text = text
        self._fail = fail

    def resolve(
        self, name: str | None = None, *, model_override: str | None = None
    ) -> JudgeModel:
        if not self.has(name):
            raise UnknownModelError(name or "default")
        return StubModel(self._text, fail=self._fail)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Start a Postgres container, create the schema, and expose its URL."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    try:
        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as exc:  # docker not running / image pull failed
        pytest.skip(f"Postgres container unavailable: {exc}")

    url = container.get_connection_url()
    os.environ["ARC_EVAL_DATABASE_URL"] = url

    from arc_eval_service.db import models as _models  # noqa: F401 - register tables
    from arc_eval_service.db.base import Base

    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    try:
        yield url
    finally:
        os.environ.pop("ARC_EVAL_DATABASE_URL", None)
        container.stop()


def _reset_caches() -> None:
    """Clear cached singletons so each test rebuilds with the current env."""
    from arc_eval_service.core import deps
    from arc_eval_service.core.config import get_settings

    for cache in (
        deps.get_database,
        deps.get_metric_registry,
        deps.get_model_registry,
        get_settings,
    ):
        cache.cache_clear()


def _truncate(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
    engine.dispose()


@pytest.fixture
def clean_db(database_url: str) -> str:
    """A truncated database plus fresh DI caches for one test."""
    _reset_caches()
    _truncate(database_url)
    return database_url


def _stub_evaluation_service() -> object:
    from arc_eval_service.core import deps
    from arc_eval_service.evaluation.service import EvaluationService

    return EvaluationService(
        cases=deps.get_case_repository(),
        results=deps.get_result_repository(),
        metrics=deps.get_metric_registry(),
        models=StubModelRegistry(),
    )


def _stub_discovery_service() -> object:
    from arc_eval_service.core import deps
    from arc_eval_service.discovery.service import DiscoveryService

    return DiscoveryService(
        metrics=deps.get_metric_registry(), models=StubModelRegistry()
    )


def _stub_ingest_service() -> object:
    from arc_eval_service.core import deps
    from arc_eval_service.core.config import get_settings
    from arc_eval_service.traces.ingest import IngestService

    settings = get_settings()
    return IngestService(
        evaluation=_stub_evaluation_service(),
        traces=deps.get_trace_repository(),
        self_service_name=settings.service_name,
        default_metric=settings.default_metric,
        default_model="default",
    )


@pytest.fixture
async def client(clean_db: str) -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient bound to the ASGI app, judging on a stub model."""
    from arc_eval_service.app import create_app
    from arc_eval_service.core import deps

    app = create_app()
    app.dependency_overrides[deps.get_evaluation_service] = _stub_evaluation_service
    app.dependency_overrides[deps.get_discovery_service] = _stub_discovery_service
    app.dependency_overrides[deps.get_ingest_service] = _stub_ingest_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
