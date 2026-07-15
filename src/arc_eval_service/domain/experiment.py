from __future__ import annotations

from pydantic import BaseModel


class ExperimentMetricAggregate(BaseModel):
    """One metric's aggregate score across an experiment's evaluated inferences."""

    metric_name: str
    average_score: float
    evaluated_count: int


class ExperimentResults(BaseModel):
    """An experiment's aggregated metric scores."""

    experiment_id: str
    metrics: list[ExperimentMetricAggregate]
