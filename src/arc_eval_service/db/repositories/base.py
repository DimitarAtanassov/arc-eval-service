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
    async def begin(self) -> AsyncIterator[AsyncSession]:
        """Open a session in a write transaction (commit on success, rollback on error).

        Sibling repositories built on the same session factory can share the
        yielded session, so a request and its results are written in one
        transaction instead of two.
        """
        async with self._sessionmaker() as session, session.begin():
            yield session

    @asynccontextmanager
    async def _write(self, session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
        """Join a caller-provided transaction, or open a private one."""
        if session is not None:
            yield session
        else:
            async with self.begin() as owned:
                yield owned

    @asynccontextmanager
    async def _read(self) -> AsyncIterator[AsyncSession]:
        """Open a short-lived read-only session (no surrounding transaction)."""
        async with self._sessionmaker() as session:
            yield session
