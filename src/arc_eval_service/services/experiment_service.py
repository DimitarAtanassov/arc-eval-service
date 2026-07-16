"""Experiments: a named metric set plus a dataset, and the run that scores it.

An experiment owns the metrics it scores against and a dataset of completed
interactions. A run evaluates every dataset entry against those metrics by reusing
the same scoring core ``POST /v1/evaluate`` uses, once per entry, with the judge
fan-out bounded so a large dataset cannot overwhelm the judge. The service holds no
model and never generates: outputs arrive in the dataset, produced elsewhere.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from arc_eval_service.db.records import (
    NewDatasetEntry,
    NewExperiment,
    NewExperimentRun,
    NewRunItem,
    StoredDatasetEntry,
    StoredExperiment,
    StoredExperimentRun,
    StoredRunItem,
)
from arc_eval_service.domain.errors import (
    EmptyDatasetError,
    ExperimentNotFoundError,
    UnknownMetricError,
)
from arc_eval_service.domain.experiment import (
    ExperimentMetricAggregate,
    ExperimentResults,
)
from arc_eval_service.services.evaluation_service import ScoredEvaluation
from arc_eval_service.services.interaction import Interaction

logger = logging.getLogger("arc_eval_service.services.experiment_service")

# Cap concurrent judge fan-out per run so a large dataset cannot open thousands of
# judge calls at once. Injectable for tests; env configuration is a later refinement.
_DEFAULT_RUN_CONCURRENCY = 8
# Upper bound on how many dataset entries a single run or list pulls.
_MAX_DATASET_ENTRIES = 1000


@dataclass(frozen=True, slots=True)
class DatasetEntryInput:
    """One dataset entry a caller supplies: a completed interaction to score."""

    input_text: str
    output_text: str
    system_text: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetAddition:
    """The outcome of appending entries to an experiment's dataset."""

    experiment_id: str
    added: int
    dataset_size: int


@dataclass(frozen=True, slots=True)
class ExperimentRunResult:
    """One run: its id and status, and the per-metric aggregates it produced."""

    run_id: str
    experiment_id: str
    status: str
    dataset_size: int
    scored_count: int
    results: list[ExperimentMetricAggregate]


class Scorer(Protocol):
    """The scoring seam the service depends on (EvaluationService satisfies it)."""

    async def score(
        self, interaction: Interaction, *, correlation_id: str | None = None
    ) -> ScoredEvaluation: ...


class ExperimentStore(Protocol):
    """The experiment-persistence seam (ExperimentRepository satisfies it)."""

    async def create(self, item: NewExperiment) -> StoredExperiment: ...
    async def get(self, experiment_id: str) -> StoredExperiment | None: ...
    async def list_recent(self, limit: int) -> list[StoredExperiment]: ...
    async def aggregate_scores(
        self, experiment_id: str
    ) -> list[ExperimentMetricAggregate]: ...


class DatasetStore(Protocol):
    """The dataset-persistence seam (DatasetEntryRepository satisfies it)."""

    async def create_many(
        self, items: list[NewDatasetEntry]
    ) -> list[StoredDatasetEntry]: ...
    async def list_for_experiment(
        self, experiment_id: str, limit: int
    ) -> list[StoredDatasetEntry]: ...
    async def count_for_experiment(self, experiment_id: str) -> int: ...
    async def counts_for_experiments(
        self, experiment_ids: list[str]
    ) -> dict[str, int]: ...


class RunStore(Protocol):
    """The run-persistence seam (ExperimentRunRepository satisfies it)."""

    async def create(self, item: NewExperimentRun) -> StoredExperimentRun: ...


class RunItemStore(Protocol):
    """The run-item-persistence seam (RunItemRepository satisfies it)."""

    async def create_many(self, items: list[NewRunItem]) -> list[StoredRunItem]: ...


class ExperimentService:
    """Creates experiments, holds their datasets, and scores those datasets."""

    def __init__(
        self,
        *,
        experiments: ExperimentStore,
        datasets: DatasetStore,
        runs: RunStore,
        run_items: RunItemStore,
        evaluation: Scorer,
        metric_names: frozenset[str],
        concurrency: int = _DEFAULT_RUN_CONCURRENCY,
    ) -> None:
        self._experiments = experiments
        self._datasets = datasets
        self._runs = runs
        self._run_items = run_items
        self._evaluation = evaluation
        self._metric_names = metric_names
        self._concurrency = concurrency

    async def create(
        self,
        *,
        name: str,
        metrics: list[str],
        description: str | None = None,
        dataset: list[DatasetEntryInput] | None = None,
    ) -> StoredExperiment:
        """Create an experiment and, optionally, seed its dataset.

        Validates the metric set against the catalog up front (UnknownMetricError,
        surfaced as 404), so a misnamed metric fails at creation, not at run. Raises
        ExperimentNameConflictError on a duplicate name.
        """
        selected = self._validate_metrics(metrics)
        experiment_id = str(uuid4())
        created = await self._experiments.create(
            NewExperiment(
                id=experiment_id,
                name=name,
                description=description,
                metrics=list(selected),
                created_at=datetime.now(UTC),
            )
        )
        if dataset:
            await self._persist_entries(experiment_id, dataset, start=0)
        return created

    async def get(self, experiment_id: str) -> StoredExperiment:
        """Return the experiment, or raise ExperimentNotFoundError."""
        experiment = await self._experiments.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        return experiment

    async def list_recent(self, limit: int) -> list[StoredExperiment]:
        """Return the most recent experiments, newest first (bounded)."""
        return await self._experiments.list_recent(limit)

    async def dataset_size(self, experiment_id: str) -> int:
        """Return how many entries an experiment's dataset holds."""
        return await self._datasets.count_for_experiment(experiment_id)

    async def dataset_sizes(self, experiment_ids: list[str]) -> dict[str, int]:
        """Return the dataset size for each experiment (one query, for list views)."""
        return await self._datasets.counts_for_experiments(experiment_ids)

    async def list_dataset(self, experiment_id: str) -> list[StoredDatasetEntry]:
        """Return an experiment's dataset entries in position order (bounded)."""
        await self.get(experiment_id)
        return await self._datasets.list_for_experiment(
            experiment_id, _MAX_DATASET_ENTRIES
        )

    async def add_dataset(
        self, experiment_id: str, entries: list[DatasetEntryInput]
    ) -> DatasetAddition:
        """Append entries to an experiment's dataset.

        Raises ExperimentNotFoundError when the experiment does not exist. Entries are
        appended after the current last position so a later run scores them too.
        """
        await self.get(experiment_id)
        start = await self._datasets.count_for_experiment(experiment_id)
        await self._persist_entries(experiment_id, entries, start=start)
        return DatasetAddition(
            experiment_id=experiment_id,
            added=len(entries),
            dataset_size=start + len(entries),
        )

    async def run(self, experiment_id: str) -> ExperimentRunResult:
        """Score the experiment's metrics over its dataset.

        Raises ExperimentNotFoundError when absent and EmptyDatasetError (409) when the
        dataset is empty. Each entry is scored through the shared evaluation core, with
        the judge fan-out bounded by a semaphore. Run items are written after scoring so
        aggregation joins back to the scores, and the run is only recorded once its
        scores exist.
        """
        experiment = await self.get(experiment_id)
        entries = await self._datasets.list_for_experiment(
            experiment_id, _MAX_DATASET_ENTRIES
        )
        if not entries:
            raise EmptyDatasetError(experiment_id)

        run_id = str(uuid4())
        correlation_id = str(uuid4())
        scored = await self._score_entries(
            entries, tuple(experiment.metrics), correlation_id
        )

        now = datetime.now(UTC)
        await self._runs.create(
            NewExperimentRun(
                id=run_id,
                experiment_id=experiment_id,
                status="completed",
                created_at=now,
            )
        )
        await self._run_items.create_many(
            [
                NewRunItem(
                    id=str(uuid4()),
                    run_id=run_id,
                    dataset_entry_id=entry.id,
                    eval_request_id=result.request_id,
                    created_at=now,
                )
                for entry, result in scored
            ]
        )

        aggregates = _aggregate([result for _, result in scored])
        logger.info(
            "experiment run complete",
            extra={
                "correlation_id": correlation_id,
                "experiment_id": experiment_id,
                "run_id": run_id,
                "dataset_size": len(entries),
                "scored_count": len(scored),
            },
        )
        return ExperimentRunResult(
            run_id=run_id,
            experiment_id=experiment_id,
            status="completed",
            dataset_size=len(entries),
            scored_count=len(scored),
            results=aggregates,
        )

    async def results(self, experiment_id: str) -> ExperimentResults:
        """Return the experiment's latest-run metric aggregates."""
        await self.get(experiment_id)
        aggregates = await self._experiments.aggregate_scores(experiment_id)
        return ExperimentResults(experiment_id=experiment_id, metrics=aggregates)

    async def compare(
        self, experiment_id_a: str, experiment_id_b: str
    ) -> list[ExperimentResults]:
        """Return latest-run aggregates for both experiments, in the order given."""
        return [
            await self.results(experiment_id_a),
            await self.results(experiment_id_b),
        ]

    async def _score_entries(
        self,
        entries: list[StoredDatasetEntry],
        metrics: tuple[str, ...],
        correlation_id: str,
    ) -> list[tuple[StoredDatasetEntry, ScoredEvaluation]]:
        """Score every entry against the metrics, bounded by the concurrency semaphore."""
        semaphore = asyncio.Semaphore(self._concurrency)

        async def score_one(
            entry: StoredDatasetEntry,
        ) -> tuple[StoredDatasetEntry, ScoredEvaluation]:
            async with semaphore:
                scored = await self._evaluation.score(
                    Interaction(
                        input_text=entry.input_text,
                        output_text=entry.output_text,
                        metrics=metrics,
                        system_text=entry.system_text,
                    ),
                    correlation_id=correlation_id,
                )
            return entry, scored

        return list(await asyncio.gather(*(score_one(entry) for entry in entries)))

    async def _persist_entries(
        self, experiment_id: str, entries: list[DatasetEntryInput], *, start: int
    ) -> None:
        """Persist dataset entries with dense positions from ``start``."""
        now = datetime.now(UTC)
        await self._datasets.create_many(
            [
                NewDatasetEntry(
                    id=str(uuid4()),
                    experiment_id=experiment_id,
                    position=start + offset,
                    input_text=entry.input_text,
                    system_text=entry.system_text,
                    output_text=entry.output_text,
                    created_at=now,
                )
                for offset, entry in enumerate(entries)
            ]
        )

    def _validate_metrics(self, metrics: list[str]) -> tuple[str, ...]:
        """De-duplicate and validate the metrics against the catalog.

        An unknown metric is a client error (UnknownMetricError, 404), raised before
        the experiment is created so a misnamed metric never persists.
        """
        selected = tuple(dict.fromkeys(metrics))
        unknown = [name for name in selected if name not in self._metric_names]
        if unknown:
            raise UnknownMetricError(unknown)
        return selected


def _aggregate(results: list[ScoredEvaluation]) -> list[ExperimentMetricAggregate]:
    """Average score and count per metric across a run's scored entries.

    A metric that errored on an entry is absent from that entry's results, so it is
    excluded from the count rather than averaged in as a real zero.
    """
    totals: dict[str, tuple[float, int]] = {}
    for scored in results:
        for metric in scored.response.results:
            total, count = totals.get(metric.metric_name, (0.0, 0))
            totals[metric.metric_name] = (total + metric.score, count + 1)
    return [
        ExperimentMetricAggregate(
            metric_name=name,
            average_score=total / count,
            evaluated_count=count,
        )
        for name, (total, count) in sorted(totals.items())
    ]
