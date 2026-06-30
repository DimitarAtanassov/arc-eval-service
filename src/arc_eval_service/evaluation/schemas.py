"""Evaluation domain types used by the judging libraries.

The interaction under test (:class:`EvaluationCase`), the metric to score it with
(:class:`MetricSpec`) and the per-metric outcome (:class:`EvaluationResult`).
There is no aggregate: each metric produces one independent result, and any
roll-up is the caller's concern.

These types are the contract the metric and judging libraries share; they are not
tied to any HTTP endpoint.
"""

from __future__ import annotations

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
