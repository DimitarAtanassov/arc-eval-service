from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from arc_eval_service.api.schemas import (
    EvaluateResponse,
    EvaluationMetadata,
)
from arc_eval_service.clients.lab_inference_client import (
    InferenceResult,
    InferenceRunRequest,
)
from arc_eval_service.db.records import (
    NewExperiment,
    NewExperimentRun,
    StoredExperiment,
    StoredExperimentRun,
)
from arc_eval_service.domain.errors import (
    ExperimentNotFoundError,
    LabNotConfiguredError,
)
from arc_eval_service.domain.experiment import (
    ExperimentMetricAggregate,
    ExperimentResults,
    GenerationConfig,
)
from arc_eval_service.services.evaluation_service import ScoredEvaluation
from arc_eval_service.services.interaction import ResolvedInteraction

logger = logging.getLogger("arc_eval_service.services.experiment_service")


class InferenceRunner(Protocol):
    """The inference seam the service depends on (LabInferenceClient satisfies it)."""

    async def run(
        self, request: InferenceRunRequest, *, correlation_id: str | None = None
    ) -> InferenceResult: ...


class Scorer(Protocol):
    """The scoring seam the service depends on (EvaluationService satisfies it)."""

    async def score(
        self, interaction: ResolvedInteraction, *, correlation_id: str | None = None
    ) -> ScoredEvaluation: ...


class ExperimentStore(Protocol):
    """The experiment-persistence seam (ExperimentRepository satisfies it)."""

    async def create(self, item: NewExperiment) -> StoredExperiment: ...
    async def get(self, experiment_id: str) -> StoredExperiment | None: ...
    async def list_recent(self, limit: int) -> list[StoredExperiment]: ...
    async def aggregate_scores(
        self, experiment_id: str
    ) -> list[ExperimentMetricAggregate]: ...


class RunStore(Protocol):
    """The experiment-run-persistence seam (ExperimentRunRepository satisfies it)."""

    async def create(self, item: NewExperimentRun) -> StoredExperimentRun: ...


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
        experiments: ExperimentStore,
        runs: RunStore,
        lab_client: InferenceRunner | None,
        evaluation: Scorer,
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
        prompt_template: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> StoredExperiment:
        """Create an experiment. Raises ExperimentNameConflictError on a duplicate name."""
        new_exp = NewExperiment(
            id=str(uuid4()),
            name=name,
            model_name=model_name,
            generation_config=generation_config.model_dump(mode="json"),
            prompt_template=prompt_template,
            variables=variables or {},
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

        Raises ExperimentNotFoundError when the experiment does not exist,
        LabNotConfiguredError (503) when no lab is wired, ModelNotFoundError /
        ModelInactiveError when the lab rejects the model, and LabInferenceError for
        any other lab failure.
        """
        experiment = await self.get(experiment_id)
        if self._lab is None:
            raise LabNotConfiguredError(
                "lab inference client is not configured (ARC_LAB_SERVICE_URL is unset)"
            )

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
                prompt_template=experiment.prompt_template,
                variables=experiment.variables,
            ),
            correlation_id=correlation_id,
        )

        eval_request_id: str | None = None
        evaluation: EvaluateResponse | None = None
        if metrics:
            interaction = ResolvedInteraction(
                input_text=inf.input_text,
                output_text=inf.output_text,
                prompt=inf.prompt,
                metrics=tuple(metrics),
                metadata=EvaluationMetadata(
                    inference_id=inf.id,
                    model_id=inf.model_id,
                ),
            )
            scored = await self._evaluation.score(
                interaction, correlation_id=correlation_id
            )
            eval_request_id = scored.request_id
            evaluation = scored.response

        # The link row is written last, in its own transaction, on purpose: the
        # inference and its scores have already committed, so if the process dies
        # here only the (inert) link is lost. A run with no link is simply not
        # counted by aggregate_scores, never double-counted, so losing it cannot
        # corrupt an experiment's results.
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
                "eval_request_id": eval_request_id,
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
        aggregates = await self._experiments.aggregate_scores(experiment_id)
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
