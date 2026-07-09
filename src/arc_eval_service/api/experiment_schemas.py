from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from arc_eval_service.api.schemas import EvaluateResponse
from arc_eval_service.clients.lab_inference_client import InferenceResult
from arc_eval_service.db.records import StoredExperiment
from arc_eval_service.domain.experiment import (
    ExperimentMetricAggregate,
    ExperimentResults,
    GenerationConfig,
)


class GenerationConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=256, ge=1)

    def to_domain(self) -> GenerationConfig:
        return GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )


class ExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str = Field(min_length=1, description="Unique experiment name.")
    description: str | None = None
    model_name: str = Field(
        min_length=1, description="Model name to run under this experiment."
    )
    generation_config: GenerationConfigSchema = Field(
        default_factory=GenerationConfigSchema
    )


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    name: str
    description: str | None
    model_name: str
    generation_config: GenerationConfigSchema
    created_at: datetime

    @classmethod
    def from_record(cls, record: StoredExperiment) -> ExperimentResponse:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            model_name=record.model_name,
            generation_config=GenerationConfigSchema.model_validate(
                record.generation_config
            ),
            created_at=record.created_at,
        )


class ExperimentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(
        min_length=1, description="Text to run through the experiment."
    )
    metrics: list[str] | None = Field(
        default=None,
        description="Metrics to score the output against. Omit to skip evaluation.",
    )


class ExperimentRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    inference_id: str
    model_id: str
    input_text: str
    prompt: str
    output_text: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    experiment_id: str
    created_at: datetime
    evaluation: EvaluateResponse | None = None

    @classmethod
    def from_run(
        cls,
        experiment_id: str,
        inference: InferenceResult,
        evaluation: EvaluateResponse | None,
    ) -> ExperimentRunResponse:
        return cls(
            inference_id=inference.id,
            model_id=inference.model_id,
            input_text=inference.input_text,
            prompt=inference.prompt,
            output_text=inference.output_text,
            latency_ms=inference.latency_ms,
            prompt_tokens=inference.prompt_tokens,
            completion_tokens=inference.completion_tokens,
            experiment_id=experiment_id,
            created_at=inference.created_at,
            evaluation=evaluation,
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
