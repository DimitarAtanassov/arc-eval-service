"""Trace and span models.

The ingest path normalises OTLP spans into :class:`SpanRecord` and synthesises a
:class:`TraceHeader` per trace; the read path assembles stored spans into a
:class:`Trace` (a list of :class:`Span` nodes with offsets relative to the trace
start) for the control plane's waterfall.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpanRecord(BaseModel):
    """A normalised OTel span persisted for trace inspection.

    Attribute values are flattened to strings: the inspection UI renders
    key/value text and storing them uniformly keeps querying simple. Message
    content rides on span events and is deliberately not persisted here.
    """

    span_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    parent_span_id: str | None = None
    name: str = ""
    service_name: str | None = None
    kind: str | None = None
    start_unix_nano: int = Field(default=0, ge=0)
    end_unix_nano: int = Field(default=0, ge=0)
    attributes: dict[str, str] = Field(default_factory=dict)


class TraceHeader(BaseModel):
    """Trace-level identity and timing, synthesised from a trace's spans."""

    trace_id: str = Field(..., min_length=1)
    request_id: str = ""
    service_name: str | None = None
    start_unix_nano: int = Field(default=0, ge=0)
    end_unix_nano: int = Field(default=0, ge=0)


class Span(BaseModel):
    """One node in a trace's span tree, served to the control plane.

    Offsets are relative to the trace start so the UI can draw a waterfall
    without absolute timestamps.
    """

    span_id: str
    parent_span_id: str | None = Field(default=None, description="None for the root.")
    name: str
    start_offset_ms: float = Field(ge=0, description="Start, relative to trace start.")
    duration_ms: float = Field(ge=0)
    attributes: dict[str, str] = Field(default_factory=dict)


class Trace(BaseModel):
    """A full trace: the span tree for one request."""

    trace_id: str
    request_id: str
    duration_ms: float = Field(ge=0)
    spans: list[Span]


class IngestResponse(BaseModel):
    """Acknowledgement for an accepted OTLP traces batch."""

    accepted: int = Field(ge=0, description="Number of evaluable interactions queued.")
    spans: int = Field(default=0, ge=0, description="Number of spans persisted.")
