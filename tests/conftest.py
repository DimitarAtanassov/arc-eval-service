"""Shared test fixtures.

A session-scoped Postgres testcontainer backs every DB-touching test; pure-logic
unit tests need none of it. The ``client`` fixture binds an httpx client to the
ASGI app with no judge model configured (so metrics error and no scores are
returned); ``stub_client`` overrides only the judge model so the happy path
(score -> persist -> respond) runs end to end without a network call.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from arc_eval_service.judging.ports import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry

# Truncated child-first; CASCADE covers the foreign key either way.
_TABLES = ("evaluation_results", "eval_requests")

# A judge verdict that parses to a passing score, used by ``stub_client``.
_STUB_VERDICT = '{"score": 0.9, "label": "pass", "explanation": "grounded in the source"}'


class _StubModel:
    """A judge model that returns a fixed passing verdict (no network)."""

    provider = "stub"
    name = "stub-judge"

    async def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        settings: ModelSettings,
        response_schema: type[BaseModel] | None = None,
    ) -> ModelCompletion:
        return ModelCompletion(text=_STUB_VERDICT, model=self.name)


class _StubModelRegistry(ModelRegistry):
    """A model registry that always resolves to :class:`_StubModel`."""

    def __init__(self) -> None:
        super().__init__(
            [ModelProfile(name="default", provider="openai_compatible", model="stub")],
            default="default",
        )

    def resolve(
        self, name: str | None = None, *, model_override: str | None = None
    ) -> JudgeModel:
        return _StubModel()


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
    from arc_eval_service.api import dependencies as deps
    from arc_eval_service.core.config import get_settings

    for cache in (deps.get_database, deps.get_catalog, get_settings):
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


@pytest.fixture
async def client(clean_db: str) -> AsyncIterator[AsyncClient]:
    """A client bound to the ASGI app with no judge model configured."""
    from arc_eval_service.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def stub_client(clean_db: str) -> AsyncIterator[AsyncClient]:
    """A client whose judge model is stubbed to a fixed passing verdict.

    Only the model call is faked: the real service, engine, metrics, repositories
    and database run, so the score -> persist -> respond path is exercised end to
    end without a network judge model.
    """
    from arc_eval_service.api.dependencies import get_database, get_evaluation_service
    from arc_eval_service.app import create_app
    from arc_eval_service.catalog import load_catalog
    from arc_eval_service.db.repositories import (
        EvalRequestRepository,
        EvaluationResultRepository,
    )
    from arc_eval_service.judging.engine import JudgeEngine
    from arc_eval_service.services.evaluation_service import EvaluationService

    def _build_service() -> EvaluationService:
        database = get_database()
        library = load_catalog()
        engine = JudgeEngine(
            library=library, models=_StubModelRegistry(), default_judge="default"
        )
        return EvaluationService(
            engine=engine,
            library=library,
            requests=EvalRequestRepository(database.sessionmaker),
            results=EvaluationResultRepository(database.sessionmaker),
        )

    app = create_app()
    app.dependency_overrides[get_evaluation_service] = _build_service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
