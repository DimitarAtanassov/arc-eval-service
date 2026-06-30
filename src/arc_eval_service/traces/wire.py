"""OTLP/HTTP traces export envelope (the JSON subset we parse).

The collector fans spans to us as OTLP/HTTP JSON; we model only the fields the
evaluator reads. ``extra="ignore"`` keeps us tolerant of the full OTLP shape, and
``alias_generator=to_camel`` matches the proto-JSON camelCase on the wire. These
types are internal (prefixed ``_``); the only public name is
:class:`OTLPTracePayload`, the request body the endpoint binds.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _OTLPBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class _ArrayValue(_OTLPBase):
    values: list[_AnyValue] = Field(default_factory=list)


class _KeyValueList(_OTLPBase):
    values: list[_KeyValue] = Field(default_factory=list)


class _AnyValue(_OTLPBase):
    """An OTLP ``AnyValue`` -- only one field is set per the proto-JSON oneof."""

    string_value: str | None = None
    bool_value: bool | None = None
    # int64 is encoded as a JSON string in proto3 JSON; accept either form.
    int_value: int | str | None = None
    double_value: float | None = None
    array_value: _ArrayValue | None = None
    kvlist_value: _KeyValueList | None = None


class _KeyValue(_OTLPBase):
    key: str
    value: _AnyValue = Field(default_factory=_AnyValue)


class _Event(_OTLPBase):
    name: str = ""
    attributes: list[_KeyValue] = Field(default_factory=list)


class _Span(_OTLPBase):
    name: str = ""
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    kind: int | str | None = None
    start_time_unix_nano: int | str | None = None
    end_time_unix_nano: int | str | None = None
    attributes: list[_KeyValue] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)


class _Resource(_OTLPBase):
    attributes: list[_KeyValue] = Field(default_factory=list)


class _ScopeSpans(_OTLPBase):
    spans: list[_Span] = Field(default_factory=list)


class _ResourceSpans(_OTLPBase):
    resource: _Resource = Field(default_factory=_Resource)
    scope_spans: list[_ScopeSpans] = Field(default_factory=list)


class OTLPTracePayload(_OTLPBase):
    """The OTLP/HTTP traces export envelope (the subset we read)."""

    resource_spans: list[_ResourceSpans] = Field(default_factory=list)


# Resolve the forward references created by the recursive ``AnyValue`` oneof.
_ArrayValue.model_rebuild()
_KeyValueList.model_rebuild()
_AnyValue.model_rebuild()
