"""The single evaluation route: score one completed interaction, inline or by id.

Selecting the use-case is request wiring, not business logic. No orchestration or
persistence lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from arc_eval_service.api.dependencies import (
    get_correlation_id,
    get_evaluation_coordinator,
)
from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.services.evaluation_coordinator import EvaluationCoordinator

router = APIRouter(tags=["evaluation"])

CoordinatorDep = Annotated[EvaluationCoordinator, Depends(get_evaluation_coordinator)]
CorrelationIdDep = Annotated[str, Depends(get_correlation_id)]


@router.post("/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(
    request: EvaluateRequest,
    coordinator: CoordinatorDep,
    correlation_id: CorrelationIdDep,
) -> EvaluateResponse:
    """Score one interaction (sent inline, or resolved from the lab by inference_id)."""
    return await coordinator.evaluate(request, correlation_id=correlation_id)
