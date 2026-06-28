"""Route definitions only.

Routes delegate straight to the service layer and shape nothing themselves. No
orchestration, scoring or persistence logic lives here. Selecting sync vs async
execution is request wiring (scheduling a background task), not business logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from arc_eval_service.api.schemas import (
    BatchEvaluateRequest,
    EvaluateRequest,
    HealthResponse,
)
from arc_eval_service.core.config import Settings, get_settings
from arc_eval_service.core.deps import get_evaluation_service
from arc_eval_service.schemas.models import (
    EvaluationRecord,
    EvaluatorInfo,
    ExecutionMode,
)
from arc_eval_service.services.evaluation import EvaluationService

router = APIRouter()

ServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok", service=settings.service_name)


@router.post("/v1/evaluate", response_model=EvaluationRecord, tags=["evaluations"])
async def evaluate(
    request: EvaluateRequest,
    service: ServiceDep,
    background: BackgroundTasks,
) -> EvaluationRecord:
    """Evaluate one interaction synchronously or asynchronously.

    With ``mode="sync"`` the completed record is returned inline. With
    ``mode="async"`` a PENDING record is returned immediately and the evaluation
    runs in the background; poll ``GET /v1/evaluations/{id}`` for the result.
    """
    if request.mode is ExecutionMode.ASYNC:
        record = await service.submit(request)
        background.add_task(service.run_async, record.evaluation_id, request)
        return record
    return await service.evaluate(request)


@router.post(
    "/v1/evaluate/batch",
    response_model=list[EvaluationRecord],
    tags=["evaluations"],
)
async def evaluate_batch(
    request: BatchEvaluateRequest,
    service: ServiceDep,
    settings: SettingsDep,
) -> list[EvaluationRecord]:
    """Evaluate a batch of interactions synchronously, preserving order."""
    if len(request.items) > settings.max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"batch size {len(request.items)} exceeds "
            f"max_batch_size ({settings.max_batch_size})",
        )
    return await service.batch(request.items)


@router.get(
    "/v1/evaluations/{evaluation_id}",
    response_model=EvaluationRecord,
    tags=["evaluations"],
)
async def get_evaluation(evaluation_id: str, service: ServiceDep) -> EvaluationRecord:
    """Return a stored evaluation record by id."""
    return await service.get(evaluation_id)


@router.get("/v1/evaluators", response_model=list[EvaluatorInfo], tags=["evaluators"])
async def list_evaluators(service: ServiceDep) -> list[EvaluatorInfo]:
    """List the registered evaluators and their descriptions."""
    return service.evaluators()
