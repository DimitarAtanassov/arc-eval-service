"""Shared test fixtures.

A session-scoped Postgres testcontainer backs every DB-touching test; pure-logic
unit tests need none of it. The ``client`` fixture binds an httpx client to the
ASGI app against the test database. No model or network is involved: the
ingestion endpoint only stores data.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

# Truncated child-first; CASCADE covers the foreign keys either way.
_TABLES = ("evaluation_runs", "eval_inputs", "metrics", "prompt_templates")


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

    for cache in (deps.get_database, get_settings):
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
    """An httpx AsyncClient bound to the ASGI app, against the test database."""
    from arc_eval_service.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
