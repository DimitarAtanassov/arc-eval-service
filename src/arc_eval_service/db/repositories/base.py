"""Shared session mechanics for repositories.

A thin **concrete** base (not an interface): every repository is constructed with
the same async session factory and opens sessions the same two ways -- a
read-only session and a write transaction. Centralising that here keeps each
repository focused on its queries and gives one place to evolve transaction
policy (isolation level, retries, instrumentation) for every repository at once.

This is a shared base, not an abstraction with a single implementation: there are
three concrete subclasses and no second backend, so no repository interface is
introduced (that would be speculative).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class BaseRepository:
    """Holds the session factory and the read / write-transaction idioms."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """Open a short-lived read-only session."""
        async with self._sessionmaker() as session:
            yield session

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        """Open a session wrapped in a transaction (commit on success, rollback on error)."""
        async with self._sessionmaker() as session, session.begin():
            yield session
