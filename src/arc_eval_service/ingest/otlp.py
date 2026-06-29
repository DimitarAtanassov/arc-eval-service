"""OTel offline ingestion (inbound adapter).

The gateway emits content-bearing LLM spans; the collector fans every span out to
this service as OTLP/HTTP **JSON**. We parse the subset we need (no proto
dependency) for two orthogonal purposes:

1. **Span store** -- every addressable span is normalised into a
   :class:`SpanRecord` and persisted (idempotent upsert keyed on ``span_id``), so
   the control plane can render the *real* span tree with its ``arc.*``
   attributes for both inference and evaluation traces.
2. **Offline judging** -- ``arc.llm.call`` spans that carry a response are mapped
   into :class:`EvaluationCase` objects and scheduled for LLM-as-a-judge scoring.

Both mappings are pure functions so they unit-test from a canned payload. Spans
originating from this service itself are stored but never re-judged: the
evaluator wraps its own judge calls in ``arc.llm.call`` spans, so judging them
would feed the collector, which fans them back here -- an unbounded loop.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from arc_telemetry.conventions import (
    ArcAttributes,
    EventNames,
    LLMAttributes,
    ResourceKeys,
    SpanNames,
)
from arc_telemetry.tracing.llm import Role
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRequest,
    JudgeSpec,
    SpanRecord,
)
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.storage.spans import SpanStore

logger = logging.getLogger("arc_eval_service.ingest.otlp")


# --- OTLP/HTTP JSON subset (camelCase via alias generator) ----------------


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


# --- service (imperative shell) -------------------------------------------


class OfflineIngestService:
    """Stores ingested spans and judges evaluable cases offline (best-effort)."""

    def __init__(
        self,
        *,
        evaluation: EvaluationService,
        spans: SpanStore,
        self_service_name: str,
        default_judge: str,
        default_model: str | None,
    ) -> None:
        self._evaluation = evaluation
        self._spans = spans
        self._self_service_name = self_service_name
        self._default_judge = default_judge
        self._default_model = default_model

    def parse(
        self, payload: OTLPTracePayload
    ) -> tuple[list[SpanRecord], list[EvaluationCase]]:
        """Return the persistable spans and evaluable cases in ``payload`` (pure)."""
        spans = parse_spans(payload)
        cases = spans_to_cases(payload, self_service_name=self._self_service_name)
        return spans, cases

    async def store(self, spans: list[SpanRecord]) -> None:
        """Persist spans (idempotent upsert); never fail the request on store."""
        if not spans:
            return
        try:
            await self._spans.upsert_many(spans)
        except Exception:
            logger.exception("span store failed", extra={"spans": len(spans)})

    async def run(self, cases: list[EvaluationCase]) -> None:
        """Judge each case offline; isolate failures so one bad case is contained."""
        spec = JudgeSpec(judge=self._default_judge, model=self._default_model)
        for case in cases:
            try:
                await self._evaluation.evaluate(
                    EvaluationRequest(case=case, judges=[spec])
                )
            except Exception:
                logger.exception(
                    "offline evaluation failed", extra={"request_id": case.request_id}
                )
