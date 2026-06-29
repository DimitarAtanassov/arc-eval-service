"""Local Pydantic domain models.

These describe the evaluation domain: the interaction under test
(:class:`EvaluationCase`), the judges to run against it (:class:`JudgeSpec`), the
per-judge outcome (:class:`EvaluationResult`) and the persisted aggregate
(:class:`EvaluationRecord`).

The evaluator runs **LLM-as-a-judge only**: every score comes from a judge
(a prompt + parser) executed on a configured model. Judges and models are
orthogonal — any judge runs on any model profile.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# Judge config values are intentionally scalar: this keeps configs JSON-safe,
# strictly typed (no ``Any``) and trivially validated. Multi-line prompts for the
# custom judge are still plain strings.
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
    """A single AI interaction to be judged.

    ``input`` is the user prompt/question, ``context`` the retrieved passages a
    grounded judge checks against, ``output`` the model's answer. Each judge
    declares which of these it ``requires``; the orchestrator validates presence
    before calling a model.
    """

    request_id: str = Field(..., min_length=1, description="Originating request id.")
    input: str | None = Field(default=None, description="User prompt / question.")
    output: str | None = Field(default=None, description="Model response text.")
    context: list[str] | None = Field(
        default=None, description="Retrieved context passages for grounded judges."
    )
    reference: str | None = Field(default=None, description="Expected/reference text.")
    metadata: dict[str, str] = Field(default_factory=dict)


class JudgeSpec(BaseModel):
    """Names a judge from the registry, the model profile to run it on, and config.

    ``model`` is a server-side model *profile* name (credentials resolved at
    boot); ``model_override`` optionally swaps the concrete model id within that
    profile. ``config`` carries per-judge knobs (e.g. the custom judge's rubric).
    """

    judge: str = Field(..., min_length=1, description="Judge registry key.")
    model: str | None = Field(
        default=None, description="Model profile name; default profile when omitted."
    )
    model_override: str | None = Field(
        default=None, description="Override the model id within the profile."
    )
    config: dict[str, ConfigValue] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    """A case plus the judges to run against it."""

    case: EvaluationCase
    judges: list[JudgeSpec] = Field(..., min_length=1)


class EvaluationResult(BaseModel):
    """Outcome of running one judge against one case.

    ``latency_ms`` is measured by the orchestrator. ``label`` and ``explanation``
    are the judge's verdict and rationale; ``model`` records which model id served
    the judgement (provenance for re-runs and audit).
    """

    judge: str
    model: str | None = None
    score: float = Field(..., ge=0.0, le=1.0)
    passed: bool
    label: str | None = None
    explanation: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None


class EvaluationRecord(BaseModel):
    """Persisted aggregate of an evaluation request across all its judges.

    ``case`` echoes the interaction that was judged, making the record
    self-describing and re-runnable. ``specs`` records the judges/models used;
    ``rerun_of`` links a re-run back to its parent evaluation.
    """

    evaluation_id: str
    request_id: str
    status: EvaluationStatus
    mode: ExecutionMode
    results: list[EvaluationResult] = Field(default_factory=list)
    aggregate_score: float | None = None
    passed: bool | None = None
    created_at: datetime
    completed_at: datetime | None = None
    case: EvaluationCase | None = None
    specs: list[JudgeSpec] = Field(default_factory=list)
    rerun_of: str | None = None


class JudgeInfo(BaseModel):
    """Discovery metadata for a registered judge."""

    name: str
    description: str
    requires: list[str]


class ModelProfileInfo(BaseModel):
    """Discovery metadata for a configured model profile (no secrets)."""

    name: str
    provider: str
    model: str
    base_url: str | None = None


class SpanRecord(BaseModel):
    """A normalised OTel span persisted for trace inspection.

    Captured from the OTLP/HTTP ingest stream so the control plane can render the
    real span tree (identity, lineage, timing and the low-cardinality ``arc.*``
    attributes) rather than reconstructing one from latency estimates. Attribute
    values are flattened to strings: the inspection UI renders key/value text and
    storing them uniformly keeps querying simple. Variable-size message content
    rides on span events and is deliberately not persisted here.
    """

    span_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    parent_span_id: str | None = None
    name: str = ""
    service_name: str | None = None
    kind: str | None = None
    start_unix_nano: int = Field(default=0, ge=0)
    end_unix_nano: int = Field(default=0, ge=0)
    attributes: dict[str, str] = Field(default_factory=dict)


class Span(BaseModel):
    """One node in a trace's span tree, as served to the control plane.

    Offsets are relative to the root span start so the UI can draw a waterfall
    without absolute per-span timestamps. ``attributes`` carries the span's
    ``arc.*`` keys (model, tokens, scores, ...) for inspection.
    """

    span_id: str
    parent_span_id: str | None = Field(default=None, description="None for the root.")
    name: str
    start_offset_ms: float = Field(ge=0, description="Start, relative to trace start.")
    duration_ms: float = Field(ge=0)
    attributes: dict[str, str] = Field(default_factory=dict)


class Trace(BaseModel):
    """A full trace: the span tree for one request."""

    trace_id: str
    request_id: str
    duration_ms: float = Field(ge=0)
    spans: list[Span]
