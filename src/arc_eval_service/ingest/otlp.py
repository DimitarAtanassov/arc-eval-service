"""OTel offline ingestion (inbound adapter).

The gateway emits content-bearing LLM spans; the collector fans them out to this
service as OTLP/HTTP **JSON**. We parse the minimal subset we need (no proto
dependency), map ``arc.llm.call`` spans into :class:`EvaluationCase` objects
(pure), and schedule offline judging with the configured default judge + model.

The span→case mapping is a pure function so it unit-tests from a canned payload.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from arc_telemetry.conventions import (
    ArcAttributes,
    EventNames,
    LLMAttributes,
    SpanNames,
)
from arc_telemetry.tracing.llm import Role
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRequest,
    JudgeSpec,
)
from arc_eval_service.services.evaluation import EvaluationService

logger = logging.getLogger("arc_eval_service.ingest.otlp")


# --- OTLP/HTTP JSON subset (camelCase via alias generator) ----------------


class _OTLPBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class _AnyValue(_OTLPBase):
    string_value: str | None = None


class _KeyValue(_OTLPBase):
    key: str
    value: _AnyValue = Field(default_factory=_AnyValue)


class _Event(_OTLPBase):
    name: str = ""
    attributes: list[_KeyValue] = Field(default_factory=list)


class _Span(_OTLPBase):
    name: str = ""
    trace_id: str | None = None
    attributes: list[_KeyValue] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)


class _ScopeSpans(_OTLPBase):
    spans: list[_Span] = Field(default_factory=list)


class _ResourceSpans(_OTLPBase):
    scope_spans: list[_ScopeSpans] = Field(default_factory=list)


class OTLPTracePayload(_OTLPBase):
    """The OTLP/HTTP traces export envelope (the subset we read)."""

    resource_spans: list[_ResourceSpans] = Field(default_factory=list)


# --- pure mapping ---------------------------------------------------------


def _kv_to_dict(pairs: list[_KeyValue]) -> dict[str, str]:
    return {
        kv.key: kv.value.string_value
        for kv in pairs
        if kv.value.string_value is not None
    }


def _first_message_content(
    span: _Span, event_name: str, role: str | None
) -> str | None:
    """Return the content of the first matching message/choice event, if any."""
    for event in span.events:
        if event.name != event_name:
            continue
        attrs = _kv_to_dict(event.attributes)
        if role is not None and attrs.get(LLMAttributes.MESSAGE_ROLE) != role:
            continue
        content = attrs.get(LLMAttributes.MESSAGE_CONTENT)
        if content:
            return content
    return None


def spans_to_cases(payload: OTLPTracePayload) -> list[EvaluationCase]:
    """Extract evaluable interactions from ``arc.llm.call`` spans (pure).

    Content rides on span events: the user message (``arc.llm.message`` with
    role=user) becomes the case input, and the response (``arc.llm.choice``)
    becomes the output. A span is evaluable only when it carries a choice, i.e.
    the gateway ran with content capture on.
    """
    cases: list[EvaluationCase] = []
    for resource in payload.resource_spans:
        for scope in resource.scope_spans:
            for span in scope.spans:
                if span.name != SpanNames.LLM_CALL:
                    continue
                output = _first_message_content(span, EventNames.LLM_CHOICE, role=None)
                if not output:
                    continue
                attrs = _kv_to_dict(span.attributes)
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
    """Maps an OTLP batch into cases and judges them offline (best-effort)."""

    def __init__(
        self,
        *,
        evaluation: EvaluationService,
        default_judge: str,
        default_model: str | None,
    ) -> None:
        self._evaluation = evaluation
        self._default_judge = default_judge
        self._default_model = default_model

    def extract(self, payload: OTLPTracePayload) -> list[EvaluationCase]:
        """Return the evaluable cases in ``payload`` (pure, cheap)."""
        return spans_to_cases(payload)

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
