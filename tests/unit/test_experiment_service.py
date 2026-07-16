"""Unit tests for the experiment service (dataset evaluator).

The stores and the scorer are in-memory doubles, so these tests exercise the
service's own logic: metric validation at creation, dataset append positions, the
empty-dataset guard, the bounded fan-out over the dataset, and aggregation.
"""

from __future__ import annotations

import pytest

from arc_eval_service.api.schemas import EvaluateResponse, MetricResult
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
    UnknownMetricError,
)
from arc_eval_service.domain.experiment import ExperimentMetricAggregate
from arc_eval_service.services.evaluation_service import ScoredEvaluation
from arc_eval_service.services.experiment_service import (
    DatasetEntryInput,
    ExperimentService,
)
from arc_eval_service.services.interaction import Interaction

pytestmark = pytest.mark.unit


class _FakeExperiments:
    def __init__(self) -> None:
        self.items: dict[str, StoredExperiment] = {}

    async def create(self, item: NewExperiment) -> StoredExperiment:
        stored = StoredExperiment(**item.model_dump())
        self.items[item.id] = stored
        return stored

    async def get(self, experiment_id: str) -> StoredExperiment | None:
        return self.items.get(experiment_id)

    async def list_recent(self, limit: int) -> list[StoredExperiment]:
        return list(self.items.values())[:limit]

    async def aggregate_scores(
        self, experiment_id: str
    ) -> list[ExperimentMetricAggregate]:
        return []


class _FakeDatasets:
    def __init__(self) -> None:
        self.entries: list[StoredDatasetEntry] = []

    async def create_many(
        self, items: list[NewDatasetEntry]
    ) -> list[StoredDatasetEntry]:
        stored = [StoredDatasetEntry(**item.model_dump()) for item in items]
        self.entries.extend(stored)
        return stored

    async def list_for_experiment(
        self, experiment_id: str, limit: int
    ) -> list[StoredDatasetEntry]:
        rows = [e for e in self.entries if e.experiment_id == experiment_id]
        return sorted(rows, key=lambda e: e.position)[:limit]

    async def count_for_experiment(self, experiment_id: str) -> int:
        return len([e for e in self.entries if e.experiment_id == experiment_id])

    async def counts_for_experiments(self, experiment_ids: list[str]) -> dict[str, int]:
        return {eid: await self.count_for_experiment(eid) for eid in experiment_ids}


class _FakeRuns:
    def __init__(self) -> None:
        self.items: list[NewExperimentRun] = []

    async def create(self, item: NewExperimentRun) -> StoredExperimentRun:
        self.items.append(item)
        return StoredExperimentRun(**item.model_dump())


class _FakeRunItems:
    def __init__(self) -> None:
        self.items: list[NewRunItem] = []

    async def create_many(self, items: list[NewRunItem]) -> list[StoredRunItem]:
        self.items.extend(items)
        return [StoredRunItem(**item.model_dump()) for item in items]


class _FakeScorer:
    """Returns a fixed score per metric and records the interactions it scored."""

    def __init__(self, *, score: float = 0.8) -> None:
        self.score_value = score
        self.seen: list[Interaction] = []
        self._counter = 0

    async def score(
        self, interaction: Interaction, *, correlation_id: str | None = None
    ) -> ScoredEvaluation:
        self._counter += 1
        self.seen.append(interaction)
        results = [
            MetricResult(
                metric_name=metric,
                score=self.score_value,
                evaluator_name=metric,
            )
            for metric in interaction.metrics
        ]
        return ScoredEvaluation(
            request_id=f"req-{self._counter}",
            response=EvaluateResponse(results=results),
        )


def _service(
    *, scorer: _FakeScorer | None = None, metrics: frozenset[str] | None = None
) -> tuple[ExperimentService, _FakeDatasets, _FakeRuns, _FakeRunItems, _FakeScorer]:
    datasets = _FakeDatasets()
    runs = _FakeRuns()
    run_items = _FakeRunItems()
    used_scorer = scorer or _FakeScorer()
    service = ExperimentService(
        experiments=_FakeExperiments(),
        datasets=datasets,
        runs=runs,
        run_items=run_items,
        evaluation=used_scorer,
        metric_names=metrics or frozenset({"faithfulness", "answer_relevance"}),
    )
    return service, datasets, runs, run_items, used_scorer


def _entries(n: int) -> list[DatasetEntryInput]:
    return [
        DatasetEntryInput(input_text=f"in-{i}", output_text=f"out-{i}")
        for i in range(n)
    ]


async def test_create_validates_metrics_against_the_catalog() -> None:
    service, *_ = _service()
    with pytest.raises(UnknownMetricError):
        await service.create(name="e", metrics=["not-a-metric"])


async def test_create_persists_experiment_and_seed_dataset() -> None:
    service, datasets, *_ = _service()

    experiment = await service.create(
        name="e", metrics=["faithfulness"], dataset=_entries(2)
    )

    assert experiment.metrics == ["faithfulness"]
    assert await service.dataset_size(experiment.id) == 2
    assert [e.position for e in datasets.entries] == [0, 1]


async def test_add_dataset_appends_after_existing_positions() -> None:
    service, datasets, *_ = _service()
    experiment = await service.create(
        name="e", metrics=["faithfulness"], dataset=_entries(2)
    )

    addition = await service.add_dataset(experiment.id, _entries(3))

    assert addition.added == 3
    assert addition.dataset_size == 5
    assert [e.position for e in datasets.entries] == [0, 1, 2, 3, 4]


async def test_run_rejects_an_empty_dataset() -> None:
    service, *_ = _service()
    experiment = await service.create(name="e", metrics=["faithfulness"])

    with pytest.raises(EmptyDatasetError):
        await service.run(experiment.id)


async def test_run_scores_every_entry_and_aggregates() -> None:
    scorer = _FakeScorer(score=0.8)
    service, _datasets, runs, run_items, _ = _service(
        scorer=scorer, metrics=frozenset({"faithfulness"})
    )
    experiment = await service.create(
        name="e", metrics=["faithfulness"], dataset=_entries(3)
    )

    result = await service.run(experiment.id)

    # Every entry was scored, one run and one run item per entry were written.
    assert len(scorer.seen) == 3
    assert scorer.seen[0].metrics == ("faithfulness",)
    assert len(runs.items) == 1
    assert len(run_items.items) == 3
    assert result.status == "completed"
    assert result.dataset_size == 3
    assert result.scored_count == 3
    aggregate = {a.metric_name: a for a in result.results}["faithfulness"]
    assert aggregate.average_score == pytest.approx(0.8)
    assert aggregate.evaluated_count == 3


async def test_run_passes_system_text_to_the_interaction() -> None:
    scorer = _FakeScorer()
    service, *_ = _service(scorer=scorer, metrics=frozenset({"faithfulness"}))
    experiment = await service.create(name="e", metrics=["faithfulness"])
    await service.add_dataset(
        experiment.id,
        [
            DatasetEntryInput(
                input_text="in", output_text="out", system_text="be precise"
            )
        ],
    )

    await service.run(experiment.id)

    assert scorer.seen[0].system_text == "be precise"
