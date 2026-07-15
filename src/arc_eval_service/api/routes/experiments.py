"""The experiments surface: create, dataset management, run, and read-back.

Route handlers stay thin: they translate the wire request into a service call and
map the service result back to a response. Business logic lives in
:class:`ExperimentService`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from arc_eval_service.api.dependencies import get_experiment_service
from arc_eval_service.api.experiment_schemas import (
    AddDatasetRequest,
    AddDatasetResponse,
    DatasetEntryResponse,
    ExperimentComparisonResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentResultsResponse,
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
    sizes = await service.dataset_sizes([record.id for record in records])
    return [
        ExperimentResponse.from_record(record, dataset_size=sizes[record.id])
        for record in records
    ]


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    payload: ExperimentCreateRequest,
    service: ServiceDep,
) -> ExperimentResponse:
    """Create an experiment, optionally seeding its dataset. 409 on a duplicate name."""
    dataset = (
        [entry.to_input() for entry in payload.dataset] if payload.dataset else None
    )
    record = await service.create(
        name=payload.name,
        metrics=payload.metrics,
        description=payload.description,
        dataset=dataset,
    )
    return ExperimentResponse.from_record(
        record, dataset_size=len(dataset) if dataset else 0
    )


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, service: ServiceDep) -> ExperimentResponse:
    """Return one experiment by id, or 404 when absent."""
    record = await service.get(experiment_id)
    dataset_size = await service.dataset_size(experiment_id)
    return ExperimentResponse.from_record(record, dataset_size=dataset_size)


@router.post(
    "/{experiment_id}/dataset",
    response_model=AddDatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_dataset(
    experiment_id: str,
    payload: AddDatasetRequest,
    service: ServiceDep,
) -> AddDatasetResponse:
    """Append dataset entries to an experiment. 404 when the experiment is absent."""
    addition = await service.add_dataset(
        experiment_id, [entry.to_input() for entry in payload.entries]
    )
    return AddDatasetResponse.from_domain(addition)


@router.get("/{experiment_id}/dataset", response_model=list[DatasetEntryResponse])
async def list_dataset(
    experiment_id: str, service: ServiceDep
) -> list[DatasetEntryResponse]:
    """Return an experiment's dataset entries in position order. 404 when absent."""
    entries = await service.list_dataset(experiment_id)
    return [DatasetEntryResponse.from_record(entry) for entry in entries]


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_experiment(
    experiment_id: str, service: ServiceDep
) -> ExperimentRunResponse:
    """Score the experiment's metrics over its dataset. 409 when the dataset is empty."""
    result = await service.run(experiment_id)
    return ExperimentRunResponse.from_domain(result)


@router.get("/{experiment_id}/results", response_model=ExperimentResultsResponse)
async def get_results(
    experiment_id: str, service: ServiceDep
) -> ExperimentResultsResponse:
    """Return the experiment's latest-run metric aggregates."""
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
    """Compare latest-run aggregates across two experiments."""
    return ExperimentComparisonResponse.from_domain(
        await service.compare(experiment_id, other_id)
    )
