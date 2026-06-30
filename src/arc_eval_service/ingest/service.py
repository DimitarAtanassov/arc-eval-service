"""OTel offline ingestion service (imperative shell).

Stores ingested spans and judges evaluable cases offline (best-effort). Spans
originating from this service itself are stored but never re-judged: the
evaluator wraps its own judge calls in ``arc.llm.call`` spans, so judging them
would feed the collector, which fans them back here -- an unbounded loop.
"""

from __future__ import annotations

import logging

from arc_eval_service.ingest.mapping import parse_spans, spans_to_cases
from arc_eval_service.ingest.wire import OTLPTracePayload
from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRequest,
    JudgeSpec,
    SpanRecord,
)
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.storage.spans import SpanStore

logger = logging.getLogger("arc_eval_service.ingest.service")


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
