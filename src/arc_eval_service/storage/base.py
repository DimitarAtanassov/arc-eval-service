"""Persistence abstraction for evaluation records.

Higher layers depend on this interface only, never on a concrete backend. The
MVP ships an in-memory implementation; a Postgres-backed store can be dropped in
behind the same contract without touching the service layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from arc_eval_service.schemas.models import EvaluationRecord


class EvaluationStore(ABC):
    """Async persistence contract for :class:`EvaluationRecord` aggregates."""

    @abstractmethod
    async def create(self, record: EvaluationRecord) -> None:
        """Persist a new record."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, record: EvaluationRecord) -> None:
        """Replace an existing record (matched by ``evaluation_id``)."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, evaluation_id: str) -> EvaluationRecord:
        """Return one record or raise :class:`NotFoundError`."""
        raise NotImplementedError

    @abstractmethod
    async def list_recent(self, limit: int) -> list[EvaluationRecord]:
        """Return up to ``limit`` records, most recently created first."""
        raise NotImplementedError

    async def dispose(self) -> None:
        """Release any held resources on shutdown.

        No-op by default (e.g. the in-memory store); backends that hold a
        connection pool override this to close it gracefully.
        """
        return None
