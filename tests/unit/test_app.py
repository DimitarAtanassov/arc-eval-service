"""Unit tests for application assembly and DI edge cases (no live database).

``create_app`` builds the app without touching the database; the connection pool
is only opened lazily and disposed on shutdown, both of which are exercised here
against a fake URL (the engine never connects).
"""

from __future__ import annotations

import pytest

from arc_eval_service.api import dependencies as deps
from arc_eval_service.core.config import get_settings

pytestmark = pytest.mark.unit

_FAKE_URL = "postgresql+psycopg://user:pass@localhost:5432/arc_eval"


def _reset_caches() -> None:
    for cache in (deps.get_database, deps.get_catalog, get_settings):
        cache.cache_clear()


def test_get_database_requires_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARC_EVAL_DATABASE_URL", raising=False)
    _reset_caches()
    try:
        with pytest.raises(RuntimeError, match="ARC_EVAL_DATABASE_URL"):
            deps.get_database()
    finally:
        _reset_caches()


async def test_lifespan_disposes_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARC_EVAL_DATABASE_URL", _FAKE_URL)
    _reset_caches()
    from arc_eval_service.app import create_app

    app = create_app()
    database = deps.get_database()  # cached; the lifespan resolves the same instance

    disposed = False

    async def _dispose() -> None:
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(database, "dispose", _dispose)

    try:
        async with app.router.lifespan_context(app):
            pass
        assert disposed is True
    finally:
        _reset_caches()
