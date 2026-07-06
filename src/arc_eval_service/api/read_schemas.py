"""Wire contract for the read (browse) endpoints.

Read-only projections of the storage records and the metric catalog, shaped for
the console. The write contract (``POST /v1/evaluate``) lives in
:mod:`arc_eval_service.api.schemas`; keeping the read DTOs here means the browse
surface can evolve without touching the scoring contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from arc_eval_service.catalog.metric.definition import MetricDefinition
from arc_eval_service.db.records import StoredEvalRequest, StoredEvaluationResult

_PREVIEW_CHARS = 160


def _preview(text: str, limit: int = _PREVIEW_CHARS) -> str:
    """Collapse whitespace and truncate to a single-line table preview."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "\u2026"


class MetricSummary(BaseModel):
    """A metric the service can score against (catalog projection)."""

    name: str
    version: str
    rubric: str
    requires: list[str]
    threshold: float

    @classmethod
    def from_definition(cls, name: str, definition: MetricDefinition) -> MetricSummary:
        return cls(
            name=name,
            version=definition.version,
            rubric=definition.rubric,
            requires=list(definition.requires),
            threshold=definition.threshold,
        )


class EvalRequestSummary(BaseModel):
    """A compact eval-request row for the browse table (previews, not full text)."""

    id: str
    input_preview: str
    output_preview: str
    inference_id: str | None
    model_id: str | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: StoredEvalRequest) -> EvalRequestSummary:
        return cls(
            id=record.id,
            input_preview=_preview(record.input_text),
            output_preview=_preview(record.output_text),
            inference_id=record.inference_id,
            model_id=record.model_id,
            created_at=record.created_at,
        )


class MetricScoreView(BaseModel):
    """One persisted metric score, shaped for the results table."""

    id: str
    eval_request_id: str
    inference_id: str | None
    model_id: str | None
    metric_name: str
    score: float
    passed: bool
    reasoning: str | None
    evaluator_name: str
    evaluator_version: str | None
    latency_ms: float
    error: str | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: StoredEvaluationResult) -> MetricScoreView:
        return cls(
            id=record.id,
            eval_request_id=record.eval_request_id,
            inference_id=record.inference_id,
            model_id=record.model_id,
            metric_name=record.metric_name,
            score=record.score,
            passed=record.passed,
            reasoning=record.reasoning,
            evaluator_name=record.evaluator_name,
            evaluator_version=record.evaluator_version,
            latency_ms=record.latency_ms,
            error=record.error,
            created_at=record.created_at,
        )


class EvalRequestDetail(BaseModel):
    """A full eval request plus every metric score recorded against it."""

    id: str
    input_text: str
    output_text: str
    prompt: str | None
    inference_id: str | None
    model_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
    results: list[MetricScoreView]

    @classmethod
    def from_records(
        cls, request: StoredEvalRequest, results: list[StoredEvaluationResult]
    ) -> EvalRequestDetail:
        return cls(
            id=request.id,
            input_text=request.input_text,
            output_text=request.output_text,
            prompt=request.prompt,
            inference_id=request.inference_id,
            model_id=request.model_id,
            metadata=request.request_metadata,
            created_at=request.created_at,
            results=[MetricScoreView.from_record(result) for result in results],
        )
