"""Shared test fixtures.

The DI factories in :mod:`arc_eval_service.core.deps` are cached singletons (the
in-memory store in particular). ``reset_state`` clears those caches before every
test so state never leaks across tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from arc_eval_service.api.main import create_app
from arc_eval_service.core import deps
from arc_eval_service.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    """Clear cached singletons so each test starts with a fresh store."""
    deps.get_store.cache_clear()
    deps.get_registry.cache_clear()
    get_settings.cache_clear()
    yield
    deps.get_store.cache_clear()
    deps.get_registry.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient bound to the ASGI app (no network)."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
