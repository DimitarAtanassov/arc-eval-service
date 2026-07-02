"""Shared session mechanics for repositories.

A thin **concrete** base (not an interface): every repository is constructed with
the same async session factory and opens a write transaction the same way.
Centralising that here keeps each repository focused on its queries and gives one
place to evolve transaction policy (isolation level, retries, instrumentation) for
every repository at once.

This is a shared base, not an abstraction with a single implementation: there are
two concrete subclasses and no second backend, so no repository interface is
introduced (that would be speculative).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class BaseRepository:
    """Holds the session factory and the write-transaction idiom."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        """Open a session wrapped in a transaction (commit on success, rollback on error)."""
        async with self._sessionmaker() as session, session.begin():
            yield session
