from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from arc_eval_service.api.schemas import (
    EvaluateRequest,
    EvaluateResponse,
    EvaluationMetadata,
)
from arc_eval_service.clients.lab_inference_client import (
    InferenceResult,
    InferenceRunRequest,
    LabInferenceClient,
)
from arc_eval_service.db.records import (
    NewExperiment,
    NewExperimentRun,
    StoredExperiment,
)
from arc_eval_service.db.repositories.experiments import (
    ExperimentRepository,
    ExperimentRunRepository,
)
from arc_eval_service.domain.errors import ExperimentNotFoundError
from arc_eval_service.domain.experiment import (
    ExperimentMetricAggregate,
    ExperimentResults,
    GenerationConfig,
)
from arc_eval_service.services.evaluation_service import EvaluationService

logger = logging.getLogger("arc_eval_service.services.experiment_service")


@dataclass(frozen=True)
class ExperimentRunResult:
    """One experiment run: the inference and, when scored, its evaluation."""

    inference: InferenceResult
    eval_request_id: str | None
    evaluation: EvaluateResponse | None


class ExperimentService:
    """Creates experiments and runs them through inference and evaluation."""

    def __init__(
        self,
        *,
        experiments: ExperimentRepository,
        runs: ExperimentRunRepository,
        lab_client: LabInferenceClient | None,
        evaluation: EvaluationService,
    ) -> None:
        self._experiments = experiments
        self._runs = runs
        self._lab = lab_client
        self._evaluation = evaluation

    async def create(
        self,
        *,
        name: str,
        model_name: str,
        generation_config: GenerationConfig,
        description: str | None = None,
    ) -> StoredExperiment:
        """Create an experiment. Raises ExperimentNameConflictError on a duplicate name."""
        new_exp = NewExperiment(
            id=str(uuid4()),
            name=name,
            model_name=model_name,
            generation_config=generation_config.model_dump(mode="json"),
            description=description,
            created_at=datetime.now(UTC),
        )
        return await self._experiments.create(new_exp)

    async def get(self, experiment_id: str) -> StoredExperiment:
        """Return the experiment, or raise ExperimentNotFoundError."""
        experiment = await self._experiments.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        return experiment

    async def list_recent(self, limit: int) -> list[StoredExperiment]:
        """Return the most recent experiments, newest first (bounded)."""
        return await self._experiments.list_recent(limit)

    async def run(
        self,
        experiment_id: str,
        input_text: str,
        *,
        metrics: list[str] | None = None,
    ) -> ExperimentRunResult:
        """Run one inference under the experiment's config, then optionally score it.

        Raises ExperimentNotFoundError when the experiment does not exist.
        Raises ModelNotFoundError/ModelInactiveError when the lab rejects the model.
        Raises LabInferenceError for any other lab failure.
        """
        if self._lab is None:
            msg = (
                "lab inference client is not configured (ARC_LAB_SERVICE_URL is unset)"
            )
            raise RuntimeError(msg)

        experiment = await self._experiments.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)

        correlation_id = str(uuid4())
        generation_config = GenerationConfig.model_validate(
            experiment.generation_config
        )
        inf = await self._lab.run(
            InferenceRunRequest(
                model_name=experiment.model_name,
                input_text=input_text,
                generation_config=generation_config,
                allow_inactive=True,
            ),
            correlation_id=correlation_id,
        )

        eval_request_id: str | None = None
        evaluation: EvaluateResponse | None = None
        if metrics:
            eval_req = EvaluateRequest(
                input_text=inf.input_text,
                output_text=inf.output_text,
                prompt=inf.prompt,
                metrics=metrics,
                metadata=EvaluationMetadata(
                    inference_id=inf.id,
                    model_id=inf.model_id,
                ),
            )
            scored = await self._evaluation.score(eval_req)
            eval_request_id = scored.request_id
            evaluation = scored.response

        new_run = NewExperimentRun(
            id=str(uuid4()),
            experiment_id=experiment_id,
            inference_id=inf.id,
            eval_request_id=eval_request_id,
            created_at=datetime.now(UTC),
        )
        await self._runs.create(new_run)

        logger.info(
            "experiment run complete",
            extra={
                "experiment_id": experiment_id,
                "inference_id": inf.id,
                "model_name": experiment.model_name,
                "latency_ms": inf.latency_ms,
                "metric_count": len(metrics) if metrics else 0,
                "correlation_id": correlation_id,
            },
        )
        return ExperimentRunResult(
            inference=inf,
            eval_request_id=eval_request_id,
            evaluation=evaluation,
        )

    async def results(self, experiment_id: str) -> ExperimentResults:
        """Return aggregated metric scores for one experiment."""
        await self.get(experiment_id)
        aggregates: list[
            ExperimentMetricAggregate
        ] = await self._experiments.aggregate_scores(experiment_id)
        return ExperimentResults(experiment_id=experiment_id, metrics=aggregates)

    async def compare(
        self,
        experiment_id_a: str,
        experiment_id_b: str,
    ) -> list[ExperimentResults]:
        """Return aggregated scores for both experiments, in the order given."""
        return [
            await self.results(experiment_id_a),
            await self.results(experiment_id_b),
        ]
