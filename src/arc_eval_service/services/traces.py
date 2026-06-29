"""Trace assembly + serving.

Reads normalised spans from the :class:`SpanStore` and assembles them into the
control plane's :class:`Trace` view: offsets relative to the trace start so the
UI can draw a waterfall. The assembly is a pure function so it unit-tests without
a store.
"""

from __future__ import annotations

from arc_telemetry.conventions import ArcAttributes

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.schemas.models import Span, SpanRecord, Trace
from arc_eval_service.storage.spans import SpanStore

# Nanoseconds per millisecond -- spans carry unix-nano timestamps.
_NANOS_PER_MS = 1_000_000.0


def _duration_ms(record: SpanRecord) -> float:
    span_ns = max(record.end_unix_nano - record.start_unix_nano, 0)
    return round(span_ns / _NANOS_PER_MS, 3)


def assemble_trace(trace_id: str, records: list[SpanRecord]) -> Trace:
    """Assemble stored spans into a waterfall-ready :class:`Trace` (pure).

    Offsets are measured from the earliest span start. ``request_id`` is read
    from whichever span carries ``arc.request_id`` (the root, by convention).
    """
    timed = [r for r in records if r.start_unix_nano > 0]
    trace_start = min((r.start_unix_nano for r in timed), default=0)
    trace_end = max((r.end_unix_nano for r in records), default=0)

    request_id = ""
    spans: list[Span] = []
    for record in sorted(records, key=lambda r: r.start_unix_nano):
        request_id = request_id or record.attributes.get(ArcAttributes.REQUEST_ID, "")
        offset_ns = max(record.start_unix_nano - trace_start, 0) if trace_start else 0
        spans.append(
            Span(
                span_id=record.span_id,
                parent_span_id=record.parent_span_id,
                name=record.name,
                start_offset_ms=round(offset_ns / _NANOS_PER_MS, 3),
                duration_ms=_duration_ms(record),
                attributes=record.attributes,
            )
        )

    duration_ms = round(max(trace_end - trace_start, 0) / _NANOS_PER_MS, 3)
    return Trace(
        trace_id=trace_id,
        request_id=request_id,
        duration_ms=duration_ms,
        spans=spans,
    )


class TraceService:
    """Serves full trace trees from the span store."""

    def __init__(self, spans: SpanStore) -> None:
        self._spans = spans

    async def get_trace(self, trace_id: str) -> Trace:
        """Return the span tree for ``trace_id`` or raise :class:`NotFoundError`."""
        records = await self._spans.get_trace(trace_id)
        if not records:
            raise NotFoundError("trace", trace_id)
        return assemble_trace(trace_id, records)
