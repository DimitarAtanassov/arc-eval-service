"""Postgres-backed :class:`EvaluationStore` (async SQLAlchemy + psycopg3).

Implements the same contract as the in-memory store, so nothing in the service
layer changes when this backend is selected (via ``ARC_EVAL_DATABASE_URL``). The
record <-> row mapping is kept in pure functions so it can be unit-tested without
a live database.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.schemas.models import (
    EvaluationRecord,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
)
from arc_eval_service.storage.base import EvaluationStore
from arc_eval_service.storage.orm import EvaluationRow


def record_to_row(record: EvaluationRecord) -> EvaluationRow:
    """Build a new ORM row from a domain record."""
    return EvaluationRow(
        evaluation_id=record.evaluation_id,
        request_id=record.request_id,
        status=record.status.value,
        mode=record.mode.value,
        results=[r.model_dump(mode="json") for r in record.results],
        aggregate_score=record.aggregate_score,
        passed=record.passed,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


def apply_record(record: EvaluationRecord, row: EvaluationRow) -> None:
    """Copy mutable fields from a domain record onto an existing row."""
    row.request_id = record.request_id
    row.status = record.status.value
    row.mode = record.mode.value
    row.results = [r.model_dump(mode="json") for r in record.results]
    row.aggregate_score = record.aggregate_score
    row.passed = record.passed
    row.created_at = record.created_at
    row.completed_at = record.completed_at


def row_to_record(row: EvaluationRow) -> EvaluationRecord:
    """Build a domain record from an ORM row."""
    return EvaluationRecord(
        evaluation_id=row.evaluation_id,
        request_id=row.request_id,
        status=EvaluationStatus(row.status),
        mode=ExecutionMode(row.mode),
        results=[EvaluationResult.model_validate(r) for r in row.results],
        aggregate_score=row.aggregate_score,
        passed=row.passed,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


class PostgresEvaluationStore(EvaluationStore):
    """Persist evaluation records to Postgres via async SQLAlchemy sessions."""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, future=True)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def create(self, record: EvaluationRecord) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(record_to_row(record))

    async def update(self, record: EvaluationRecord) -> None:
        async with self._sessionmaker() as session, session.begin():
            row = await session.get(EvaluationRow, record.evaluation_id)
            if row is None:
                raise NotFoundError("evaluation", record.evaluation_id)
            apply_record(record, row)

    async def get(self, evaluation_id: str) -> EvaluationRecord:
        async with self._sessionmaker() as session:
            row = await session.get(EvaluationRow, evaluation_id)
        if row is None:
            raise NotFoundError("evaluation", evaluation_id)
        return row_to_record(row)

    async def list_recent(self, limit: int) -> list[EvaluationRecord]:
        stmt = select(EvaluationRow).order_by(EvaluationRow.created_at.desc()).limit(limit)
        async with self._sessionmaker() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [row_to_record(row) for row in rows]

    async def dispose(self) -> None:
        """Dispose the engine's connection pool (call on shutdown)."""
        await self._engine.dispose()
