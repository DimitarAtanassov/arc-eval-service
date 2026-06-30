"""Evaluation routes: delegate straight to the service.

Selecting batch limits is request wiring, not business logic. No orchestration,
scoring or persistence lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from arc_eval_service.core.config import Settings, get_settings
from arc_eval_service.core.deps import get_evaluation_service
from arc_eval_service.evaluation.schemas import (
    BatchEvaluationRequest,
    EvaluationRequest,
    EvaluationResponse,
    RerunRequest,
)
from arc_eval_service.evaluation.service import EvaluationService

router = APIRouter(tags=["evaluations"])

ServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/v1/evaluate", response_model=EvaluationResponse)
async def evaluate(
    request: EvaluationRequest, service: ServiceDep
) -> EvaluationResponse:
    """Score one interaction against its metrics."""
    return await service.evaluate(request)


@router.post("/v1/evaluate/batch", response_model=list[EvaluationResponse])
async def evaluate_batch(
    request: BatchEvaluationRequest, service: ServiceDep, settings: SettingsDep
) -> list[EvaluationResponse]:
    """Score a batch of interactions, preserving order."""
    if len(request.items) > settings.max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"batch size {len(request.items)} exceeds "
            f"max_batch_size ({settings.max_batch_size})",
        )
    return await service.batch(request.items)


@router.get("/v1/evaluations", response_model=list[EvaluationResponse])
async def list_evaluations(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EvaluationResponse]:
    """List recent evaluations, most recently created first."""
    return await service.recent(limit)


@router.get("/v1/evaluations/{case_id}", response_model=EvaluationResponse)
async def get_evaluation(case_id: str, service: ServiceDep) -> EvaluationResponse:
    """Return a stored evaluation (case + results) by case id."""
    return await service.get(case_id)


@router.post("/v1/evaluations/{case_id}/rerun", response_model=EvaluationResponse)
async def rerun_evaluation(
    case_id: str, request: RerunRequest, service: ServiceDep
) -> EvaluationResponse:
    """Re-score a stored case, optionally with different metrics."""
    return await service.rerun(case_id, request.metrics)


@router.delete("/v1/evaluations/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluation(case_id: str, service: ServiceDep) -> None:
    """Delete a stored evaluation (404 if it does not exist)."""
    await service.delete(case_id)
