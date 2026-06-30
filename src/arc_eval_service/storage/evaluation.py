"""Evaluation record persistence (one vertical slice).

The store contract (:class:`EvaluationStore`), its in-memory and Postgres
implementations, the ORM row and the record<->row mappers live together so
"how does evaluation storage work?" is answered in one file. Adding a backend
means adding a class here, not editing four files. The mappers are pure so they
unit-test without a live database.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, mapped_column

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRecord,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
    JudgeSpec,
)
from arc_eval_service.storage.orm import Base

# --- ORM row ---------------------------------------------------------------


class EvaluationRow(Base):
    """Row representation of one :class:`EvaluationRecord`."""

    __tablename__ = "evaluations"

    evaluation_id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    results: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    case: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    specs: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    rerun_of: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    aggregate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --- store contract --------------------------------------------------------


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

    @abstractmethod
    async def delete(self, evaluation_id: str) -> None:
        """Delete one record or raise :class:`NotFoundError` if it is absent."""
        raise NotImplementedError

    async def dispose(self) -> None:
        """Release any held resources on shutdown.

        No-op by default (e.g. the in-memory store); backends that hold a
        connection pool override this to close it gracefully.
        """
        return None


# --- in-memory backend -----------------------------------------------------


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

    async def delete(self, evaluation_id: str) -> None:
        async with self._lock:
            if self._records.pop(evaluation_id, None) is None:
                raise NotFoundError("evaluation", evaluation_id)


# --- record <-> row mappers (pure) -----------------------------------------


def _case_to_json(record: EvaluationRecord) -> dict[str, object] | None:
    return record.case.model_dump(mode="json") if record.case is not None else None


def record_to_row(record: EvaluationRecord) -> EvaluationRow:
    """Build a new ORM row from a domain record."""
    return EvaluationRow(
        evaluation_id=record.evaluation_id,
        request_id=record.request_id,
        status=record.status.value,
        mode=record.mode.value,
        results=[r.model_dump(mode="json") for r in record.results],
        case=_case_to_json(record),
        specs=[s.model_dump(mode="json") for s in record.specs],
        rerun_of=record.rerun_of,
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
    row.case = _case_to_json(record)
    row.specs = [s.model_dump(mode="json") for s in record.specs]
    row.rerun_of = record.rerun_of
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
        case=EvaluationCase.model_validate(row.case) if row.case is not None else None,
        specs=[JudgeSpec.model_validate(s) for s in row.specs],
        rerun_of=row.rerun_of,
        aggregate_score=row.aggregate_score,
        passed=row.passed,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


# --- Postgres backend ------------------------------------------------------


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
        stmt = (
            select(EvaluationRow).order_by(EvaluationRow.created_at.desc()).limit(limit)
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [row_to_record(row) for row in rows]

    async def delete(self, evaluation_id: str) -> None:
        async with self._sessionmaker() as session, session.begin():
            row = await session.get(EvaluationRow, evaluation_id)
            if row is None:
                raise NotFoundError("evaluation", evaluation_id)
            await session.delete(row)

    async def dispose(self) -> None:
        """Dispose the engine's connection pool (call on shutdown)."""
        await self._engine.dispose()
