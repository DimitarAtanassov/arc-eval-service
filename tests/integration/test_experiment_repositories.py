from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from arc_eval_service.db.engine import Database
from arc_eval_service.db.records import (
    NewEvalRequest,
    NewEvaluationResult,
    NewExperiment,
    NewExperimentRun,
)
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.db.repositories.experiments import (
    ExperimentRepository,
    ExperimentRunRepository,
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
    prompt_template: str | None = None,
    variables: dict[str, str] | None = None,
) -> NewExperiment:
    return NewExperiment(
        id=exp_id,
        name=name,
        model_name="candidate",
        generation_config={"temperature": 0.0, "max_output_tokens": 64},
        prompt_template=prompt_template,
        variables=variables or {},
        description="first run",
        created_at=datetime.now(UTC),
    )


def _run(
    run_id: str, exp_id: str, inference_id: str, eval_request_id: str | None
) -> NewExperimentRun:
    return NewExperimentRun(
        id=run_id,
        experiment_id=exp_id,
        inference_id=inference_id,
        eval_request_id=eval_request_id,
        created_at=datetime.now(UTC),
    )


def _eval_request(req_id: str, inference_id: str = "inf-1") -> NewEvalRequest:
    return NewEvalRequest(
        id=req_id,
        input_text="source",
        output_text="summary",
        prompt="Summarize:",
        inference_id=inference_id,
        model_id="mdl-1",
        request_metadata={},
    )


def _result(
    result_id: str, req_id: str, metric: str, score: float, error: str | None = None
) -> NewEvaluationResult:
    return NewEvaluationResult(
        id=result_id,
        eval_request_id=req_id,
        inference_id="inf-1",
        model_id="mdl-1",
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


async def test_create_get_and_list(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    stored = await experiments.create(_experiment())

    assert stored.id == "exp-1"
    fetched = await experiments.get("exp-1")
    assert fetched is not None
    assert fetched.name == "baseline"
    by_name = await experiments.get_by_name("baseline")
    assert by_name is not None
    assert by_name.id == "exp-1"
    assert await experiments.get("missing") is None
    assert await experiments.get_by_name("missing") is None
    assert [e.id for e in await experiments.list_recent(10)] == ["exp-1"]


async def test_create_persists_prompt_template_and_variables(
    database: Database,
) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    await experiments.create(
        _experiment(
            prompt_template="translate", variables={"target_language": "French"}
        )
    )

    fetched = await experiments.get("exp-1")
    assert fetched is not None
    assert fetched.prompt_template == "translate"
    assert fetched.variables == {"target_language": "French"}


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


async def test_run_repository_persists_link(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    requests = EvalRequestRepository(database.sessionmaker)
    runs = ExperimentRunRepository(database.sessionmaker)

    await experiments.create(_experiment())
    await requests.create(_eval_request("req-1"))
    stored = await runs.create(_run("run-1", "exp-1", "inf-1", "req-1"))

    assert stored.eval_request_id == "req-1"


async def test_aggregate_filters_errors_and_dedups_by_eval_request(
    database: Database,
) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    requests = EvalRequestRepository(database.sessionmaker)
    results = EvaluationResultRepository(database.sessionmaker)
    runs = ExperimentRunRepository(database.sessionmaker)

    await experiments.create(_experiment())
    await requests.create(_eval_request("req-1"))
    await results.create_many(
        [
            _result("r1", "req-1", "faithfulness", 0.8),
            _result("r2", "req-1", "relevance", 0.6),
            _result("r3", "req-1", "faithfulness", 0.0, error="judge down"),
        ]
    )
    # A later re-evaluation of the same inference the run does NOT link to.
    await requests.create(_eval_request("req-2"))
    await results.create_many([_result("r4", "req-2", "faithfulness", 0.2)])

    await runs.create(_run("run-1", "exp-1", "inf-1", "req-1"))

    aggregates = {a.metric_name: a for a in await experiments.aggregate_scores("exp-1")}

    assert aggregates["faithfulness"].average_score == pytest.approx(0.8)
    assert aggregates["faithfulness"].evaluated_count == 1
    assert aggregates["relevance"].average_score == pytest.approx(0.6)


async def test_aggregate_empty_when_no_runs(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    await experiments.create(_experiment())
    assert await experiments.aggregate_scores("exp-1") == []
