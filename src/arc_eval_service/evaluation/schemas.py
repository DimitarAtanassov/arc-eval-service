"""Evaluation domain models and HTTP DTOs.

The core domain language of the service: the interaction under test
(:class:`EvaluationCase`), the metrics to score it with (:class:`MetricSpec`),
and the per-metric outcome (:class:`EvaluationResult`). There is no aggregate:
each metric produces one independent result, and any roll-up is the caller's
concern.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

type ConfigValue = str | int | float | bool


class EvaluationCase(BaseModel):
    """A single AI interaction to be scored.

    Each metric declares which fields it ``requires``; the engine degrades a
    metric to an errored result when a required field is absent.
    """

    request_id: str = Field(..., min_length=1, description="Originating request id.")
    input: str | None = Field(default=None, description="User prompt / question.")
    output: str | None = Field(default=None, description="Model response text.")
    context: list[str] | None = Field(
        default=None, description="Retrieved context passages for grounded metrics."
    )
    reference: str | None = Field(default=None, description="Expected/reference text.")
    metadata: dict[str, str] = Field(default_factory=dict)


class MetricSpec(BaseModel):
    """Names a metric, the model profile to score it on, and any config.

    ``model`` is a server-side profile name; ``model_override`` swaps the concrete
    model id within that profile. ``config`` carries per-metric knobs (e.g. the
    custom metric's rubric or a ``pass_threshold`` override).
    """

    metric: str = Field(..., min_length=1, description="Metric registry key.")
    model: str | None = Field(
        default=None, description="Model profile name; default profile when omitted."
    )
    model_override: str | None = Field(
        default=None, description="Override the model id within the profile."
    )
    config: dict[str, ConfigValue] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Outcome of scoring one metric against one case.

    ``passed`` is the metric's own threshold applied to ``score`` (not an
    aggregate). ``model`` records which model id served the judgement.
    """

    metric: str
    model: str | None = None
    score: float = Field(..., ge=0.0, le=1.0)
    passed: bool
    label: str | None = None
    explanation: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None


class EvaluationRequest(BaseModel):
    """A case plus the metrics to score it with."""

    case: EvaluationCase
    metrics: list[MetricSpec] = Field(..., min_length=1)


class BatchEvaluationRequest(BaseModel):
    """A batch of evaluation requests, scored in order."""

    items: list[EvaluationRequest] = Field(..., min_length=1)


class RerunRequest(BaseModel):
    """Re-score a stored case, optionally with different metrics.

    When ``metrics`` is omitted the metrics from the prior results are reused.
    """

    metrics: list[MetricSpec] | None = Field(default=None, min_length=1)


class StoredCase(BaseModel):
    """A persisted eval-ready case: the interaction plus its storage identity."""

    case_id: str
    trace_id: str | None = None
    created_at: datetime
    case: EvaluationCase


class EvaluationResponse(BaseModel):
    """A stored case with its per-metric results (the read model)."""

    case_id: str
    request_id: str
    trace_id: str | None = None
    created_at: datetime
    results: list[EvaluationResult] = Field(default_factory=list)

    @classmethod
    def of(
        cls, stored: StoredCase, results: list[EvaluationResult]
    ) -> EvaluationResponse:
        """Compose a response from a stored case and its results."""
        return cls(
            case_id=stored.case_id,
            request_id=stored.case.request_id,
            trace_id=stored.trace_id,
            created_at=stored.created_at,
            results=results,
        )
