from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from arc_eval_service.db.engine import Database
from arc_eval_service.db.records import (
    NewDatasetEntry,
    NewEvalRequest,
    NewEvaluationResult,
    NewExperiment,
    NewExperimentRun,
    NewRunItem,
)
from arc_eval_service.db.repositories import (
    DatasetEntryRepository,
    EvalRequestRepository,
    EvaluationResultRepository,
    ExperimentRepository,
    ExperimentRunRepository,
    RunItemRepository,
)
from arc_eval_service.domain.errors import ExperimentNameConflictError

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(clean_db: str) -> AsyncIterator[Database]:
    db = Database(clean_db)
    yield db
    await db.dispose()


def _experiment(
    exp_id: str = "exp-1",
    name: str = "baseline",
    *,
    metrics: list[str] | None = None,
) -> NewExperiment:
    return NewExperiment(
        id=exp_id,
        name=name,
        description="first run",
        metrics=metrics if metrics is not None else ["faithfulness"],
        created_at=datetime.now(UTC),
    )


def _run(
    run_id: str, exp_id: str, *, created_at: datetime | None = None
) -> NewExperimentRun:
    return NewExperimentRun(
        id=run_id,
        experiment_id=exp_id,
        status="completed",
        created_at=created_at or datetime.now(UTC),
    )


def _entry(entry_id: str, exp_id: str, position: int = 0) -> NewDatasetEntry:
    return NewDatasetEntry(
        id=entry_id,
        experiment_id=exp_id,
        position=position,
        input_text="src",
        system_text=None,
        output_text="out",
        created_at=datetime.now(UTC),
    )


def _eval_request(req_id: str) -> NewEvalRequest:
    return NewEvalRequest(
        id=req_id,
        input_text="src",
        output_text="out",
        prompt=None,
        inference_id=None,
        model_id=None,
        request_metadata={},
    )


def _result(
    result_id: str, req_id: str, metric: str, score: float, error: str | None = None
) -> NewEvaluationResult:
    return NewEvaluationResult(
        id=result_id,
        eval_request_id=req_id,
        inference_id=None,
        model_id=None,
        metric_name=metric,
        score=score,
        passed=score >= 0.5,
        reasoning=None,
        evaluator_name=metric,
        evaluator_version="v1",
        judge=None,
        prompt=None,
        latency_ms=1.0,
        error=error,
    )


def _run_item(
    item_id: str, run_id: str, entry_id: str, req_id: str | None
) -> NewRunItem:
    return NewRunItem(
        id=item_id,
        run_id=run_id,
        dataset_entry_id=entry_id,
        eval_request_id=req_id,
        created_at=datetime.now(UTC),
    )


async def test_create_get_and_list(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    stored = await experiments.create(_experiment())

    assert stored.id == "exp-1"
    assert stored.metrics == ["faithfulness"]
    fetched = await experiments.get("exp-1")
    assert fetched is not None
    assert fetched.name == "baseline"
    by_name = await experiments.get_by_name("baseline")
    assert by_name is not None
    assert by_name.id == "exp-1"
    assert await experiments.get("missing") is None
    assert [e.id for e in await experiments.list_recent(10)] == ["exp-1"]


async def test_duplicate_name_raises_conflict(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    await experiments.create(_experiment(exp_id="exp-1", name="dup"))

    with pytest.raises(ExperimentNameConflictError):
        await experiments.create(_experiment(exp_id="exp-2", name="dup"))


async def test_duplicate_id_reraises_integrity_error(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    await experiments.create(_experiment(exp_id="exp-1", name="a"))

    with pytest.raises(IntegrityError):
        await experiments.create(_experiment(exp_id="exp-1", name="b"))


async def test_aggregate_over_latest_run_filters_errors(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    entries = DatasetEntryRepository(database.sessionmaker)
    requests = EvalRequestRepository(database.sessionmaker)
    results = EvaluationResultRepository(database.sessionmaker)
    runs = ExperimentRunRepository(database.sessionmaker)
    run_items = RunItemRepository(database.sessionmaker)

    await experiments.create(_experiment())
    await entries.create_many([_entry("e1", "exp-1", 0)])
    await requests.create(_eval_request("req-1"))
    await results.create_many(
        [
            _result("r1", "req-1", "faithfulness", 0.8),
            _result("r2", "req-1", "faithfulness", 0.0, error="judge down"),
        ]
    )
    await runs.create(_run("run-1", "exp-1"))
    await run_items.create_many([_run_item("ri-1", "run-1", "e1", "req-1")])

    aggregates = {a.metric_name: a for a in await experiments.aggregate_scores("exp-1")}

    # The errored score is excluded, so only the successful 0.8 is averaged.
    assert aggregates["faithfulness"].average_score == pytest.approx(0.8)
    assert aggregates["faithfulness"].evaluated_count == 1


async def test_aggregate_uses_only_the_latest_run(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    entries = DatasetEntryRepository(database.sessionmaker)
    requests = EvalRequestRepository(database.sessionmaker)
    results = EvaluationResultRepository(database.sessionmaker)
    runs = ExperimentRunRepository(database.sessionmaker)
    run_items = RunItemRepository(database.sessionmaker)

    await experiments.create(_experiment())
    await entries.create_many([_entry("e1", "exp-1", 0)])
    # An earlier run scored 0.2; the latest run scored 0.9. Only the latest counts.
    await requests.create(_eval_request("req-1"))
    await results.create_many([_result("r1", "req-1", "faithfulness", 0.2)])
    await runs.create(
        _run("run-1", "exp-1", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    )
    await run_items.create_many([_run_item("ri-1", "run-1", "e1", "req-1")])

    await requests.create(_eval_request("req-2"))
    await results.create_many([_result("r2", "req-2", "faithfulness", 0.9)])
    await runs.create(
        _run("run-2", "exp-1", created_at=datetime(2026, 1, 2, tzinfo=UTC))
    )
    await run_items.create_many([_run_item("ri-2", "run-2", "e1", "req-2")])

    aggregates = {a.metric_name: a for a in await experiments.aggregate_scores("exp-1")}

    assert aggregates["faithfulness"].average_score == pytest.approx(0.9)
    assert aggregates["faithfulness"].evaluated_count == 1


async def test_aggregate_empty_when_no_runs(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    await experiments.create(_experiment())
    assert await experiments.aggregate_scores("exp-1") == []
