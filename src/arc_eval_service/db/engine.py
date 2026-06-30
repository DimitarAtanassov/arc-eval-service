"""Async engine + session factory (one per process).

The service is Postgres-only: a single async engine backs a session factory that
every repository opens short-lived sessions from. There is no in-memory backend;
the database URL is required configuration.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Owns the async engine and the session factory for the process."""

    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(url, future=True)
        self.sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def dispose(self) -> None:
        """Dispose the engine's connection pool (call on shutdown)."""
        await self._engine.dispose()
