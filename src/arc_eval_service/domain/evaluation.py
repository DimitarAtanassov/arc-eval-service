"""Domain evaluation types shared by the judging engine, prompts, and services.

The interaction under test (:class:`EvaluationCase`) and the per-metric outcome
(:class:`MetricScore`). There is no aggregate: each metric produces one
independent score, and any roll-up is the caller's concern. These types are pure
data with no framework dependencies, which is what lets the lower layers depend on
them without a cycle.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class MetricScore(BaseModel):
    """Outcome of scoring one metric against one case.

    ``passed`` is the metric's own threshold applied to ``score`` (not an
    aggregate). ``model`` records which model id served the judgement. The
    provenance fields (``provider`` through ``max_tokens``) record how the score
    was produced; they are persisted for audit and are not returned to callers.
    """

    metric: str
    model: str | None = None
    score: float = Field(..., ge=0.0, le=1.0)
    passed: bool
    label: str | None = None
    explanation: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None

    # Judge-call provenance (persisted, not returned).
    judge_name: str | None = None
    judge_version: str | None = None
    provider: str | None = None
    prompt_template: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
