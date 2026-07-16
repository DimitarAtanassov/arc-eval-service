"""Wire contract for the experiments surface.

An experiment owns a metric set and a dataset of completed interactions. Requests
create an experiment (optionally seeding its dataset), append dataset entries, and
run the metrics over the dataset. Responses expose the experiment, the dataset, and
per-metric aggregates. The service-layer result types are mapped here so the routes
stay thin.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from arc_eval_service.db.records import StoredDatasetEntry, StoredExperiment
from arc_eval_service.domain.experiment import (
    ExperimentMetricAggregate,
    ExperimentResults,
)
from arc_eval_service.services.experiment_service import (
    DatasetAddition,
    DatasetEntryInput,
    ExperimentRunResult,
)


class DatasetEntryRequest(BaseModel):
    """One completed interaction to add to an experiment's dataset."""

    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(min_length=1, description="The original input.")
    output_text: str = Field(min_length=1, description="The output to score.")
    system_text: str | None = Field(
        default=None, min_length=1, description="Optional system prompt used."
    )

    def to_input(self) -> DatasetEntryInput:
        return DatasetEntryInput(
            input_text=self.input_text,
            output_text=self.output_text,
            system_text=self.system_text,
        )


class ExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Unique experiment name.")
    description: str | None = None
    metrics: list[str] = Field(
        min_length=1,
        description="Metrics this experiment scores its dataset against.",
    )
    dataset: list[DatasetEntryRequest] | None = Field(
        default=None,
        description="Optional dataset entries to seed the experiment with.",
    )


class ExperimentResponse(BaseModel):
    id: str
    name: str
    description: str | None
    metrics: list[str]
    dataset_size: int
    created_at: datetime

    @classmethod
    def from_record(
        cls, record: StoredExperiment, *, dataset_size: int
    ) -> ExperimentResponse:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            metrics=record.metrics,
            dataset_size=dataset_size,
            created_at=record.created_at,
        )


class AddDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[DatasetEntryRequest] = Field(
        min_length=1, description="Dataset entries to append."
    )


class AddDatasetResponse(BaseModel):
    experiment_id: str
    added: int
    dataset_size: int

    @classmethod
    def from_domain(cls, addition: DatasetAddition) -> AddDatasetResponse:
        return cls(
            experiment_id=addition.experiment_id,
            added=addition.added,
            dataset_size=addition.dataset_size,
        )


class DatasetEntryResponse(BaseModel):
    id: str
    position: int
    input_text: str
    system_text: str | None
    output_text: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: StoredDatasetEntry) -> DatasetEntryResponse:
        return cls(
            id=record.id,
            position=record.position,
            input_text=record.input_text,
            system_text=record.system_text,
            output_text=record.output_text,
            created_at=record.created_at,
        )


class MetricAggregateOut(BaseModel):
    metric_name: str
    average_score: float
    evaluated_count: int

    @classmethod
    def from_domain(cls, aggregate: ExperimentMetricAggregate) -> MetricAggregateOut:
        return cls(
            metric_name=aggregate.metric_name,
            average_score=aggregate.average_score,
            evaluated_count=aggregate.evaluated_count,
        )


class ExperimentRunResponse(BaseModel):
    run_id: str
    experiment_id: str
    status: str
    dataset_size: int
    scored_count: int
    results: list[MetricAggregateOut]

    @classmethod
    def from_domain(cls, result: ExperimentRunResult) -> ExperimentRunResponse:
        return cls(
            run_id=result.run_id,
            experiment_id=result.experiment_id,
            status=result.status,
            dataset_size=result.dataset_size,
            scored_count=result.scored_count,
            results=[MetricAggregateOut.from_domain(a) for a in result.results],
        )


class ExperimentResultsResponse(BaseModel):
    experiment_id: str
    metrics: list[MetricAggregateOut]

    @classmethod
    def from_domain(cls, result: ExperimentResults) -> ExperimentResultsResponse:
        return cls(
            experiment_id=result.experiment_id,
            metrics=[MetricAggregateOut.from_domain(a) for a in result.metrics],
        )


class ExperimentComparisonResponse(BaseModel):
    experiments: list[ExperimentResultsResponse]

    @classmethod
    def from_domain(
        cls, results: list[ExperimentResults]
    ) -> ExperimentComparisonResponse:
        return cls(
            experiments=[ExperimentResultsResponse.from_domain(r) for r in results]
        )
