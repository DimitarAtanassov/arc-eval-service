"""The single ingestion route: store one LLM interaction to evaluate later.

Selecting the service is request wiring, not business logic. No orchestration or
persistence lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from arc_eval_service.core.deps import get_ingestion_service
from arc_eval_service.ingestion.schemas import EvalInputRequest, EvalInputResponse
from arc_eval_service.ingestion.service import IngestionService

router = APIRouter(tags=["ingestion"])

ServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]


@router.post(
    "/v1/eval-inputs",
    response_model=EvalInputResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_eval_input(
    request: EvalInputRequest, service: ServiceDep
) -> EvalInputResponse:
    """Store one LLM interaction: prompt template, inputs, response and config."""
    return await service.record(request)
