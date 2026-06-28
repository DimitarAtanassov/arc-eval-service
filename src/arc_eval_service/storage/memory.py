"""In-memory :class:`EvaluationStore` (MVP persistence).

Thread/task-safe via an ``asyncio.Lock``. Records are stored as immutable
Pydantic models, so callers cannot mutate persisted state by reference.
"""

from __future__ import annotations

import asyncio

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.schemas.models import EvaluationRecord
from arc_eval_service.storage.base import EvaluationStore


class InMemoryEvaluationStore(EvaluationStore):
    """Process-local store backed by a dict, guarded by a lock."""

    def __init__(self) -> None:
        self._records: dict[str, EvaluationRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: EvaluationRecord) -> None:
        async with self._lock:
            self._records[record.evaluation_id] = record

    async def update(self, record: EvaluationRecord) -> None:
        async with self._lock:
            if record.evaluation_id not in self._records:
                raise NotFoundError("evaluation", record.evaluation_id)
            self._records[record.evaluation_id] = record

    async def get(self, evaluation_id: str) -> EvaluationRecord:
        async with self._lock:
            record = self._records.get(evaluation_id)
        if record is None:
            raise NotFoundError("evaluation", evaluation_id)
        return record

    async def list_recent(self, limit: int) -> list[EvaluationRecord]:
        async with self._lock:
            records = list(self._records.values())
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]
