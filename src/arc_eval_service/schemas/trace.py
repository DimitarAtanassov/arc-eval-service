"""Trace and span models served to the control plane.

The ingest path normalises OTLP spans into :class:`SpanRecord` for storage; the
read path assembles them into a :class:`Trace` (a tree of :class:`Span` nodes
with offsets relative to the trace start) for the UI's waterfall.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpanRecord(BaseModel):
    """A normalised OTel span persisted for trace inspection.

    Captured from the OTLP/HTTP ingest stream so the control plane can render the
    real span tree (identity, lineage, timing and the low-cardinality ``arc.*``
    attributes) rather than reconstructing one from latency estimates. Attribute
    values are flattened to strings: the inspection UI renders key/value text and
    storing them uniformly keeps querying simple. Variable-size message content
    rides on span events and is deliberately not persisted here.
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


class Span(BaseModel):
    """One node in a trace's span tree, as served to the control plane.

    Offsets are relative to the root span start so the UI can draw a waterfall
    without absolute per-span timestamps. ``attributes`` carries the span's
    ``arc.*`` keys (model, tokens, scores, ...) for inspection.
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
