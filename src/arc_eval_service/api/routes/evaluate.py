"""The single evaluation route: score one completed interaction inline.

Selecting the service is request wiring, not business logic. No orchestration or
persistence lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from arc_eval_service.api.dependencies import get_evaluation_service
from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.services.evaluation_service import EvaluationService

router = APIRouter(tags=["evaluation"])

ServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]


@router.post("/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest, service: ServiceDep) -> EvaluateResponse:
    """Score one interaction across the requested metrics and return the results."""
    return await service.evaluate(request)
