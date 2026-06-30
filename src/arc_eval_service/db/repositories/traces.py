"""Persistence for the trace aggregate: trace headers and their spans.

The :class:`TraceRepository` owns both the ``traces`` and ``spans`` tables (a
trace and its spans are one aggregate) plus the pure row <-> domain mappers for
each. Writes are idempotent upserts: the collector may redeliver spans and
children may arrive before parents.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from arc_eval_service.db.models import SpanRow, TraceRow
from arc_eval_service.db.repositories.base import BaseRepository
from arc_eval_service.traces.schemas import SpanRecord, TraceHeader


def span_to_values(record: SpanRecord) -> dict[str, object]:
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


def row_to_span(row: SpanRow) -> SpanRecord:
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


def header_to_values(header: TraceHeader) -> dict[str, object]:
    return {
        "trace_id": header.trace_id,
        "request_id": header.request_id,
        "service_name": header.service_name,
        "start_unix_nano": header.start_unix_nano,
        "end_unix_nano": header.end_unix_nano,
    }


def row_to_header(row: TraceRow) -> TraceHeader:
    return TraceHeader(
        trace_id=row.trace_id,
        request_id=row.request_id,
        service_name=row.service_name,
        start_unix_nano=row.start_unix_nano,
        end_unix_nano=row.end_unix_nano,
    )


class TraceRepository(BaseRepository):
    """Persistence for the trace aggregate: trace headers and their spans."""

    _SPAN_UPSERT_COLUMNS = (
        "trace_id",
        "parent_span_id",
        "name",
        "service_name",
        "kind",
        "start_unix_nano",
        "end_unix_nano",
        "attributes",
    )
    _HEADER_UPSERT_COLUMNS = (
        "request_id",
        "service_name",
        "start_unix_nano",
        "end_unix_nano",
    )

    async def upsert_headers(self, headers: list[TraceHeader]) -> None:
        if not headers:
            return
        stmt = insert(TraceRow).values([header_to_values(h) for h in headers])
        stmt = stmt.on_conflict_do_update(
            index_elements=[TraceRow.trace_id],
            set_={col: stmt.excluded[col] for col in self._HEADER_UPSERT_COLUMNS},
        )
        async with self._transaction() as session:
            await session.execute(stmt)

    async def upsert_spans(self, spans: list[SpanRecord]) -> None:
        if not spans:
            return
        stmt = insert(SpanRow).values([span_to_values(s) for s in spans])
        stmt = stmt.on_conflict_do_update(
            index_elements=[SpanRow.span_id],
            set_={col: stmt.excluded[col] for col in self._SPAN_UPSERT_COLUMNS},
        )
        async with self._transaction() as session:
            await session.execute(stmt)

    async def get_header(self, trace_id: str) -> TraceHeader | None:
        async with self._session() as session:
            row = await session.get(TraceRow, trace_id)
        return row_to_header(row) if row is not None else None

    async def get_spans(self, trace_id: str) -> list[SpanRecord]:
        stmt = (
            select(SpanRow)
            .where(SpanRow.trace_id == trace_id)
            .order_by(SpanRow.start_unix_nano)
        )
        async with self._session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [row_to_span(row) for row in rows]
