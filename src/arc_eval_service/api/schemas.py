"""API request/response models.

These wrap the domain models from :mod:`arc_eval_service.schemas.models` with
HTTP-only concerns (such as the execution ``mode`` and batch envelope).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from arc_eval_service.schemas.models import EvaluationRequest, ExecutionMode


class EvaluateRequest(EvaluationRequest):
    """A single evaluation request plus its desired execution mode."""

    mode: ExecutionMode = ExecutionMode.SYNC


class BatchEvaluateRequest(BaseModel):
    """A batch of synchronous evaluation requests."""

    items: list[EvaluationRequest] = Field(..., min_length=1)


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = "ok"
    service: str
