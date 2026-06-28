"""Local Pydantic domain models.

These describe the evaluation domain: the interaction under test
(:class:`EvaluationCase`), the evaluators to run (:class:`EvaluatorSpec`), the
per-evaluator outcome (:class:`EvaluationResult`) and the persisted aggregate
(:class:`EvaluationRecord`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# Evaluator config values are intentionally scalar: this keeps configs JSON-safe,
# strictly typed (no ``Any``) and trivially validated by the evaluator helpers.
type ConfigValue = str | int | float | bool


class ExecutionMode(StrEnum):
    """Whether the caller wants the result inline or via later polling."""

    SYNC = "sync"
    ASYNC = "async"


class EvaluationStatus(StrEnum):
    """Lifecycle of an :class:`EvaluationRecord`."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationCase(BaseModel):
    """A single AI interaction to be evaluated.

    All signal fields are optional; each evaluator declares (by raising
    :class:`~arc_eval_service.core.errors.EvaluationError`) which fields it
    requires.
    """

    request_id: str = Field(..., min_length=1, description="Originating request id.")
    output: str | None = Field(default=None, description="Model response text.")
    reference: str | None = Field(default=None, description="Expected/reference text.")
    latency_ms: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class EvaluatorSpec(BaseModel):
    """Names an evaluator from the registry plus its per-call configuration."""

    name: str = Field(..., min_length=1, description="Registry key, e.g. 'regex'.")
    config: dict[str, ConfigValue] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    """A case plus the evaluators to run against it."""

    case: EvaluationCase
    evaluators: list[EvaluatorSpec] = Field(..., min_length=1)


class EvaluatorInput(BaseModel):
    """The argument passed to ``Evaluator.evaluate``."""

    case: EvaluationCase
    config: dict[str, ConfigValue] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Outcome of running one evaluator against one case.

    ``latency_ms`` is measured by the orchestrator (not the evaluator) and
    overwritten after the call returns.
    """

    evaluator_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    passed: bool
    latency_ms: float = Field(default=0.0, ge=0.0)
    details: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class EvaluationRecord(BaseModel):
    """Persisted aggregate of an evaluation request across all its evaluators."""

    evaluation_id: str
    request_id: str
    status: EvaluationStatus
    mode: ExecutionMode
    results: list[EvaluationResult] = Field(default_factory=list)
    aggregate_score: float | None = None
    passed: bool | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvaluatorInfo(BaseModel):
    """Discovery metadata for a registered evaluator."""

    name: str
    description: str
