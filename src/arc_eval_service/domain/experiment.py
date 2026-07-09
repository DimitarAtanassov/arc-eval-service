from __future__ import annotations

from pydantic import BaseModel, Field


class GenerationConfig(BaseModel):
    """Decoding parameters for one generation request."""

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=256, ge=1)


class ExperimentMetricAggregate(BaseModel):
    """One metric's aggregate score across an experiment's evaluated inferences."""

    metric_name: str
    average_score: float
    evaluated_count: int


class ExperimentResults(BaseModel):
    """An experiment's aggregated metric scores."""

    experiment_id: str
    metrics: list[ExperimentMetricAggregate]
