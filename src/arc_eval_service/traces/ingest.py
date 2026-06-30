"""OTel offline ingestion service (imperative shell).

Stores ingested traces/spans and judges evaluable cases offline (best-effort).
Spans originating from this service itself are stored but never re-judged: the
evaluator wraps its own judge calls in ``arc.llm.call`` spans, so judging them
would feed the collector, which fans them back here -- an unbounded loop.
"""

from __future__ import annotations

import logging

from arc_eval_service.db.repositories import TraceRepository
from arc_eval_service.evaluation.schemas import (
    EvaluationCase,
    EvaluationRequest,
    MetricSpec,
)
from arc_eval_service.evaluation.service import EvaluationService
from arc_eval_service.traces.mapping import (
    build_trace_headers,
    parse_spans,
    spans_to_cases,
)
from arc_eval_service.traces.schemas import SpanRecord, TraceHeader
from arc_eval_service.traces.wire import OTLPTracePayload

logger = logging.getLogger("arc_eval_service.traces.ingest")


class IngestService:
    """Stores ingested traces/spans and judges evaluable cases (best-effort)."""

    def __init__(
        self,
        *,
        evaluation: EvaluationService,
        traces: TraceRepository,
        self_service_name: str,
        default_metric: str,
        default_model: str | None,
    ) -> None:
        self._evaluation = evaluation
        self._traces = traces
        self._self_service_name = self_service_name
        self._default_metric = default_metric
        self._default_model = default_model

    def parse(
        self, payload: OTLPTracePayload
    ) -> tuple[list[SpanRecord], list[TraceHeader], list[EvaluationCase]]:
        """Return the spans, trace headers and evaluable cases in ``payload`` (pure)."""
        spans = parse_spans(payload)
        headers = build_trace_headers(spans)
        cases = spans_to_cases(payload, self_service_name=self._self_service_name)
        return spans, headers, cases

    async def store(self, spans: list[SpanRecord], headers: list[TraceHeader]) -> None:
        """Persist traces + spans (idempotent); never fail the request on store."""
        if not spans:
            return
        try:
            await self._traces.upsert_headers(headers)
            await self._traces.upsert_spans(spans)
        except Exception:
            logger.exception("trace store failed", extra={"spans": len(spans)})

    async def run(self, cases: list[EvaluationCase]) -> None:
        """Judge each case offline; isolate failures so one bad case is contained."""
        spec = MetricSpec(metric=self._default_metric, model=self._default_model)
        for case in cases:
            try:
                await self._evaluation.evaluate(
                    EvaluationRequest(case=case, metrics=[spec]),
                    trace_id=case.metadata.get("trace_id"),
                )
            except Exception:
                logger.exception(
                    "offline evaluation failed", extra={"request_id": case.request_id}
                )
