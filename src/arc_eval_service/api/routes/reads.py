"""Read (browse) endpoints: the metric catalog and persisted evaluations.

Reads only. Selecting the service is request wiring, not business logic; no
orchestration or persistence lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from arc_eval_service.api.dependencies import get_read_service
from arc_eval_service.api.read_schemas import (
    EvalRequestDetail,
    EvalRequestSummary,
    MetricScoreView,
    MetricSummary,
)
from arc_eval_service.services.read_service import ReadService

router = APIRouter(prefix="/v1", tags=["reads"])

ServiceDep = Annotated[ReadService, Depends(get_read_service)]

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
LimitDep = Annotated[int, Query(ge=1, le=_MAX_LIMIT)]


@router.get("/metrics", response_model=list[MetricSummary])
async def list_metrics(service: ServiceDep) -> list[MetricSummary]:
    """List the metrics the service can score an interaction against."""
    return [
        MetricSummary.from_definition(name, definition)
        for name, definition in service.metrics.items()
    ]


@router.get("/requests", response_model=list[EvalRequestSummary])
async def list_requests(
    service: ServiceDep, limit: LimitDep = _DEFAULT_LIMIT
) -> list[EvalRequestSummary]:
    """List recent interactions submitted for evaluation, newest first."""
    records = await service.list_requests(limit)
    return [EvalRequestSummary.from_record(record) for record in records]


@router.get("/requests/{request_id}", response_model=EvalRequestDetail)
async def get_request(request_id: str, service: ServiceDep) -> EvalRequestDetail:
    """Return one interaction with every metric score recorded against it, or 404."""
    found = await service.get_request(request_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"eval request not found: {request_id}",
        )
    return EvalRequestDetail.from_records(found.request, found.results)


@router.get("/results", response_model=list[MetricScoreView])
async def list_results(
    service: ServiceDep,
    limit: LimitDep = _DEFAULT_LIMIT,
    metric: Annotated[str | None, Query()] = None,
    model_id: Annotated[str | None, Query()] = None,
) -> list[MetricScoreView]:
    """List recent metric scores, newest first, optionally filtered by metric or model."""
    records = await service.list_results(limit, metric_name=metric, model_id=model_id)
    return [MetricScoreView.from_record(record) for record in records]
