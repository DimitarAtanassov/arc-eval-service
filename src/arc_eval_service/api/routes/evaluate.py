"""The single evaluation route: score one supplied interaction against named metrics.

Building the interaction from the request is thin wiring, not business logic. No
orchestration or persistence lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from arc_eval_service.api.dependencies import (
    get_correlation_id,
    get_evaluation_service,
)
from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.services.evaluation_service import EvaluationService
from arc_eval_service.services.interaction import Interaction

router = APIRouter(tags=["evaluation"])

EvaluationDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
CorrelationIdDep = Annotated[str, Depends(get_correlation_id)]


@router.post("/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(
    request: EvaluateRequest,
    evaluation: EvaluationDep,
    correlation_id: CorrelationIdDep,
) -> EvaluateResponse:
    """Score one supplied interaction against the named metrics."""
    interaction = Interaction(
        input_text=request.input_text,
        output_text=request.output_text,
        metrics=tuple(request.metrics),
    )
    scored = await evaluation.score(interaction, correlation_id=correlation_id)
    return scored.response
