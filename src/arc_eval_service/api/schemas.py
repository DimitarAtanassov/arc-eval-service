"""API request/response models.

These wrap the domain models from :mod:`arc_eval_service.schemas.models` with
HTTP-only concerns (such as the execution ``mode``, batch envelope and re-run
overrides).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from arc_eval_service.schemas.models import (
    EvaluationRequest,
    ExecutionMode,
    JudgeSpec,
)


class EvaluateRequest(EvaluationRequest):
    """A single evaluation request plus its desired execution mode."""

    mode: ExecutionMode = ExecutionMode.SYNC


class BatchEvaluateRequest(BaseModel):
    """A batch of synchronous evaluation requests."""

    items: list[EvaluationRequest] = Field(..., min_length=1)


class RerunRequest(BaseModel):
    """Re-run a stored evaluation, optionally with different judges/models.

    When ``judges`` is omitted the original specs are re-used.
    """

    judges: list[JudgeSpec] | None = Field(default=None, min_length=1)


class IngestResponse(BaseModel):
    """Acknowledgement for an accepted OTLP traces batch."""

    accepted: int = Field(ge=0, description="Number of evaluable interactions queued.")
    spans: int = Field(default=0, ge=0, description="Number of spans persisted.")


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = "ok"
    service: str
