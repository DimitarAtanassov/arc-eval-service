"""Shared test fixtures.

A session-scoped Postgres testcontainer backs every DB-touching test; pure-logic
unit tests need none of it. The ``client`` fixture binds an httpx client to the
ASGI app with no judge model configured (so metrics error and no scores are
returned); ``stub_client`` overrides only the judge model so the happy path
(score -> persist -> respond) runs end to end without a network call.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from arc_eval_service.judging.ports import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry

# Truncated child-first; CASCADE covers the foreign key either way.
_TABLES = ("evaluation_results", "eval_requests")

# A judge verdict that parses to a passing score, used by ``stub_client``.
_STUB_VERDICT = (
    '{"score": 0.9, "label": "pass", "explanation": "grounded in the source"}'
)


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


def _free_port() -> int:
    """Reserve an ephemeral TCP port for the local Postgres cluster."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _start_testcontainer() -> tuple[str, Callable[[], None]] | None:
    """Start Postgres in a container, or return ``None`` when unavailable.

    The canonical path (used in CI). Returns ``None`` when the library is missing,
    the Docker daemon is down, or the image registry is blocked.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        return None
    try:
        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception:  # any container failure (daemon down, registry blocked)
        return None
    return container.get_connection_url(), container.stop


def _start_local_postgres() -> tuple[str, Callable[[], None]] | None:
    """Start an ephemeral cluster with the on-PATH initdb/pg_ctl, or return None.

    A dev fallback for machines where the container registry is blocked. It is real
    Postgres (so ``JSONB`` columns behave as in production), initialised in a temp
    directory on a random port and discarded at session end. Returns ``None`` when
    the Postgres binaries are not installed.
    """
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if initdb is None or pg_ctl is None:
        return None

    root = Path(tempfile.mkdtemp(prefix="arc-eval-pg-"))
    data_dir = root / "data"
    port = _free_port()
    try:
        subprocess.run(  # noqa: S603 - fixed argv, executable resolved from PATH
            [initdb, "-D", str(data_dir), "-U", "postgres", "--auth=trust", "-N"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # noqa: S603 - fixed argv, executable resolved from PATH
            [
                pg_ctl,
                "-D",
                str(data_dir),
                "-w",
                "-l",
                str(root / "log"),
                "-o",
                f"-p {port} -k {root} -h 127.0.0.1",
                "start",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        shutil.rmtree(root, ignore_errors=True)
        return None

    def _stop() -> None:
        subprocess.run(  # noqa: S603 - fixed argv, executable resolved from PATH
            [pg_ctl, "-D", str(data_dir), "-m", "immediate", "-w", "stop"],
            check=False,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(root, ignore_errors=True)

    return f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres", _stop


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Provide a Postgres URL with the schema created, for the whole session.

    Prefers a testcontainer (CI); falls back to an ephemeral local cluster started
    with the on-PATH ``initdb``/``pg_ctl`` when the container registry is blocked.
    The DB-backed suite is skipped only when neither is available.
    """
    provider = _start_testcontainer() or _start_local_postgres()
    if provider is None:
        pytest.skip(
            "no Postgres available (container registry blocked, no local initdb)"
        )
    url, stop = provider
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
        stop()


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
