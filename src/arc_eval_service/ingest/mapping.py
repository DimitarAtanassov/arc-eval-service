"""Pure OTLP -> domain mapping (functional core).

Two pure functions over a parsed :class:`OTLPTracePayload`:

* :func:`parse_spans` normalises every addressable span into a
  :class:`SpanRecord` for the span store.
* :func:`spans_to_cases` extracts the evaluable ``arc.llm.call`` interactions
  into :class:`EvaluationCase` objects for offline judging.

No I/O, so both unit-test from a canned payload.
"""

from __future__ import annotations

import json
from uuid import uuid4

from arc_telemetry.conventions import (
    ArcAttributes,
    EventNames,
    LLMAttributes,
    ResourceKeys,
    SpanNames,
)
from arc_telemetry.tracing.llm import Role

from arc_eval_service.ingest.wire import (
    OTLPTracePayload,
    _AnyValue,
    _KeyValue,
    _Resource,
    _Span,
)
from arc_eval_service.schemas.models import EvaluationCase, SpanRecord

# --- pure value coercion --------------------------------------------------

# OTLP span kind enum (proto int) -> readable name, for the few values we emit.
_SPAN_KINDS = {
    1: "internal",
    2: "server",
    3: "client",
    4: "producer",
    5: "consumer",
}


def _anyvalue_to_str(value: _AnyValue) -> str | None:
    """Flatten an OTLP ``AnyValue`` to a display string (None if unset)."""
    if value.bool_value is not None:
        return "true" if value.bool_value else "false"
    if value.array_value is not None:
        items = [_anyvalue_to_str(v) for v in value.array_value.values]
        return json.dumps([item for item in items if item is not None])
    if value.kvlist_value is not None:
        return json.dumps(_attrs_to_str_dict(value.kvlist_value.values))
    # string / int64 / double are mutually exclusive scalar fields.
    if value.string_value is not None:
        return value.string_value
    if value.int_value is not None:
        return str(value.int_value)
    return str(value.double_value) if value.double_value is not None else None


def _attrs_to_str_dict(pairs: list[_KeyValue]) -> dict[str, str]:
    """Flatten a list of OTLP key/values into a string-valued dict."""
    result: dict[str, str] = {}
    for kv in pairs:
        flattened = _anyvalue_to_str(kv.value)
        if flattened is not None:
            result[kv.key] = flattened
    return result


def _to_int(value: int | str | None) -> int:
    """Coerce an OTLP unix-nano field (string in proto-JSON) to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _kind_to_str(kind: int | str | None) -> str | None:
    if kind is None:
        return None
    if isinstance(kind, str):
        return kind or None
    return _SPAN_KINDS.get(kind, str(kind))


def _resource_service_name(resource: _Resource) -> str | None:
    return _attrs_to_str_dict(resource.attributes).get(ResourceKeys.SERVICE_NAME)


# --- pure mapping: spans -> persisted records -----------------------------


def parse_spans(payload: OTLPTracePayload) -> list[SpanRecord]:
    """Normalise every addressable span in ``payload`` for the span store (pure).

    Spans without a ``span_id``/``trace_id`` cannot be placed in a trace tree, so
    they are skipped rather than stored unaddressably.
    """
    records: list[SpanRecord] = []
    for resource_spans in payload.resource_spans:
        service_name = _resource_service_name(resource_spans.resource)
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                if not span.span_id or not span.trace_id:
                    continue
                records.append(
                    SpanRecord(
                        span_id=span.span_id,
                        trace_id=span.trace_id,
                        parent_span_id=span.parent_span_id or None,
                        name=span.name,
                        service_name=service_name,
                        kind=_kind_to_str(span.kind),
                        start_unix_nano=_to_int(span.start_time_unix_nano),
                        end_unix_nano=_to_int(span.end_time_unix_nano),
                        attributes=_attrs_to_str_dict(span.attributes),
                    )
                )
    return records


# --- pure mapping: spans -> evaluable cases -------------------------------


def _first_message_content(
    span: _Span, event_name: str, role: str | None
) -> str | None:
    """Return the content of the first matching message/choice event, if any."""
    for event in span.events:
        if event.name != event_name:
            continue
        attrs = _attrs_to_str_dict(event.attributes)
        if role is not None and attrs.get(LLMAttributes.MESSAGE_ROLE) != role:
            continue
        content = attrs.get(LLMAttributes.MESSAGE_CONTENT)
        if content:
            return content
    return None


def spans_to_cases(
    payload: OTLPTracePayload, *, self_service_name: str | None = None
) -> list[EvaluationCase]:
    """Extract evaluable interactions from ``arc.llm.call`` spans (pure).

    Content rides on span events: the user message (``arc.llm.message`` with
    role=user) becomes the case input, and the response (``arc.llm.choice``)
    becomes the output. A span is evaluable only when it carries a choice, i.e.
    the emitter ran with content capture on.

    Spans whose resource ``service.name`` equals ``self_service_name`` are
    skipped: those are this evaluator's own judge calls, and judging them would
    create a feedback loop through the collector.
    """
    cases: list[EvaluationCase] = []
    for resource_spans in payload.resource_spans:
        service_name = _resource_service_name(resource_spans.resource)
        if self_service_name is not None and service_name == self_service_name:
            continue
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                if span.name != SpanNames.LLM_CALL:
                    continue
                output = _first_message_content(span, EventNames.LLM_CHOICE, role=None)
                if not output:
                    continue
                attrs = _attrs_to_str_dict(span.attributes)
                metadata = {"source": "otel"}
                if model := attrs.get(LLMAttributes.REQUEST_MODEL):
                    metadata["model"] = model
                if span.trace_id:
                    metadata["trace_id"] = span.trace_id
                cases.append(
                    EvaluationCase(
                        request_id=attrs.get(ArcAttributes.REQUEST_ID)
                        or span.trace_id
                        or str(uuid4()),
                        input=_first_message_content(
                            span, EventNames.LLM_MESSAGE, role=Role.USER
                        ),
                        output=output,
                        metadata=metadata,
                    )
                )
    return cases
