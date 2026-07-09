from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from arc_eval_service.api.dependencies import get_experiment_service
from arc_eval_service.api.experiment_schemas import (
    ExperimentComparisonResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentResultsResponse,
    ExperimentRunRequest,
    ExperimentRunResponse,
)
from arc_eval_service.services.experiment_service import ExperimentService

router = APIRouter(prefix="/v1/experiments", tags=["experiments"])

ServiceDep = Annotated[ExperimentService, Depends(get_experiment_service)]

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
LimitDep = Annotated[int, Query(ge=1, le=_MAX_LIMIT)]


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(
    service: ServiceDep,
    limit: LimitDep = _DEFAULT_LIMIT,
) -> list[ExperimentResponse]:
    """Return recent experiments, newest first (bounded page size)."""
    records = await service.list_recent(limit)
    return [ExperimentResponse.from_record(r) for r in records]


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    payload: ExperimentCreateRequest,
    service: ServiceDep,
) -> ExperimentResponse:
    """Create a new experiment. 409 when the name is already taken."""
    record = await service.create(
        name=payload.name,
        model_name=payload.model_name,
        generation_config=payload.generation_config.to_domain(),
        description=payload.description,
    )
    return ExperimentResponse.from_record(record)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, service: ServiceDep) -> ExperimentResponse:
    """Return one experiment by id, or 404 when absent."""
    return ExperimentResponse.from_record(await service.get(experiment_id))


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_experiment(
    experiment_id: str,
    payload: ExperimentRunRequest,
    service: ServiceDep,
) -> ExperimentRunResponse:
    """Run one inference under the experiment, optionally scoring the output."""
    result = await service.run(
        experiment_id, payload.input_text, metrics=payload.metrics
    )
    return ExperimentRunResponse.from_run(
        experiment_id, result.inference, result.evaluation
    )


@router.get("/{experiment_id}/results", response_model=ExperimentResultsResponse)
async def get_results(
    experiment_id: str, service: ServiceDep
) -> ExperimentResultsResponse:
    """Return aggregated metric scores for an experiment."""
    return ExperimentResultsResponse.from_domain(await service.results(experiment_id))


@router.get(
    "/{experiment_id}/compare/{other_id}",
    response_model=ExperimentComparisonResponse,
)
async def compare_experiments(
    experiment_id: str,
    other_id: str,
    service: ServiceDep,
) -> ExperimentComparisonResponse:
    """Compare aggregated scores across two experiments."""
    return ExperimentComparisonResponse.from_domain(
        await service.compare(experiment_id, other_id)
    )
