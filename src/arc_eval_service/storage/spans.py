"""Persistence for normalised OTel spans (the trace store).

Separate from :class:`~arc_eval_service.storage.base.EvaluationStore` because
spans are a different aggregate with a different lifecycle: they arrive from the
collector out of order, are written far more often than they are read, and are
keyed on ``span_id`` for idempotent upserts. Keeping the contract self-contained
here makes it cheap to extract into a dedicated telemetry store later (see
ADR-0006) without disturbing the evaluation path.

The row <-> record mapping is kept in pure functions so it unit-tests without a
live database.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from arc_eval_service.schemas.models import SpanRecord
from arc_eval_service.storage.orm import SpanRow


class SpanStore(ABC):
    """Async persistence contract for normalised spans."""

    @abstractmethod
    async def upsert_many(self, spans: list[SpanRecord]) -> None:
        """Persist spans idempotently, keyed on ``span_id`` (last write wins)."""
        raise NotImplementedError

    @abstractmethod
    async def get_trace(self, trace_id: str) -> list[SpanRecord]:
        """Return every stored span for ``trace_id`` (empty if unknown)."""
        raise NotImplementedError

    async def dispose(self) -> None:
        """Release any held resources on shutdown (no-op by default)."""
        return None


class InMemorySpanStore(SpanStore):
    """Process-local span store backed by a dict, guarded by a lock."""

    def __init__(self) -> None:
        self._spans: dict[str, SpanRecord] = {}
        self._lock = asyncio.Lock()

    async def upsert_many(self, spans: list[SpanRecord]) -> None:
        async with self._lock:
            for span in spans:
                self._spans[span.span_id] = span

    async def get_trace(self, trace_id: str) -> list[SpanRecord]:
        async with self._lock:
            return [s for s in self._spans.values() if s.trace_id == trace_id]


def record_to_row_values(record: SpanRecord) -> dict[str, object]:
    """Map a span record to the column values for an insert/upsert."""
    return {
        "span_id": record.span_id,
        "trace_id": record.trace_id,
        "parent_span_id": record.parent_span_id,
        "name": record.name,
        "service_name": record.service_name,
        "kind": record.kind,
        "start_unix_nano": record.start_unix_nano,
        "end_unix_nano": record.end_unix_nano,
        "attributes": record.attributes,
    }


def row_to_record(row: SpanRow) -> SpanRecord:
    """Build a span record from an ORM row."""
    return SpanRecord(
        span_id=row.span_id,
        trace_id=row.trace_id,
        parent_span_id=row.parent_span_id,
        name=row.name,
        service_name=row.service_name,
        kind=row.kind,
        start_unix_nano=row.start_unix_nano,
        end_unix_nano=row.end_unix_nano,
        attributes=row.attributes,
    )


class PostgresSpanStore(SpanStore):
    """Persist spans to Postgres via an ``ON CONFLICT`` upsert (idempotent)."""

    # Columns refreshed when a span is redelivered; identity columns are excluded.
    _UPSERT_COLUMNS = (
        "trace_id",
        "parent_span_id",
        "name",
        "service_name",
        "kind",
        "start_unix_nano",
        "end_unix_nano",
        "attributes",
    )

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, future=True)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def upsert_many(self, spans: list[SpanRecord]) -> None:
        if not spans:
            return
        values = [record_to_row_values(span) for span in spans]
        stmt = insert(SpanRow).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SpanRow.span_id],
            set_={col: stmt.excluded[col] for col in self._UPSERT_COLUMNS},
        )
        async with self._sessionmaker() as session, session.begin():
            await session.execute(stmt)

    async def get_trace(self, trace_id: str) -> list[SpanRecord]:
        stmt = (
            select(SpanRow)
            .where(SpanRow.trace_id == trace_id)
            .order_by(SpanRow.start_unix_nano)
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [row_to_record(row) for row in rows]

    async def dispose(self) -> None:
        """Dispose the engine's connection pool (call on shutdown)."""
        await self._engine.dispose()
