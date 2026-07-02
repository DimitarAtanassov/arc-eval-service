"""Integration tests for repositories against a real Postgres container."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from arc_eval_service.db.engine import Database
from arc_eval_service.db.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(clean_db: str) -> AsyncIterator[Database]:
    db = Database(clean_db)
    yield db
    await db.dispose()


def _new_request(request_id: str = "req-1") -> NewEvalRequest:
    return NewEvalRequest(
        id=request_id,
        task_type="summarization",
        input_text="source",
        output_text="summary",
        prompt="Summarize:",
        inference_id="inf-1",
        model_id="mdl-1",
        request_metadata={"inference_id": "inf-1", "model_id": "mdl-1"},
    )


def _new_result(request_id: str, metric: str) -> NewEvaluationResult:
    return NewEvaluationResult(
        id=f"{request_id}-{metric}",
        eval_request_id=request_id,
        inference_id="inf-1",
        model_id="mdl-1",
        metric_name=metric,
        score=0.9,
        passed=True,
        reasoning="grounded",
        evaluator_name=metric,
        evaluator_version="v1",
        judge={
            "name": "default",
            "version": "v1",
            "model": "stub-judge",
            "provider": "stub",
            "temperature": 0.0,
            "max_tokens": 1024,
            "system_prompt": "rubric",
        },
        prompt={"template": "rubric", "variables": {"output": "summary"}},
        latency_ms=1.0,
        error=None,
    )


async def test_create_request_then_results(database: Database, clean_db: str) -> None:
    requests = EvalRequestRepository(database.sessionmaker)
    results = EvaluationResultRepository(database.sessionmaker)

    await requests.create(_new_request())
    await results.create_many(
        [_new_result("req-1", "faithfulness"), _new_result("req-1", "answer_relevance")]
    )

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            req_rows = conn.execute(
                text("SELECT id, inference_id FROM eval_requests")
            ).all()
            res_rows = conn.execute(
                text(
                    "SELECT metric_name, eval_request_id, judge, prompt "
                    "FROM evaluation_results"
                )
            ).all()
    finally:
        engine.dispose()

    assert [(r.id, r.inference_id) for r in req_rows] == [("req-1", "inf-1")]
    assert {r.metric_name for r in res_rows} == {"faithfulness", "answer_relevance"}
    assert all(r.eval_request_id == "req-1" for r in res_rows)
    assert all(r.judge["model"] == "stub-judge" for r in res_rows)
    assert all(r.prompt["template"] == "rubric" for r in res_rows)


async def test_create_many_empty_is_a_noop(database: Database, clean_db: str) -> None:
    results = EvaluationResultRepository(database.sessionmaker)

    await results.create_many([])

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM evaluation_results")
            ).scalar()
    finally:
        engine.dispose()

    assert count == 0


async def test_request_and_results_persist_atomically(
    database: Database, clean_db: str
) -> None:
    """A failed results write rolls back the request in the same transaction."""
    requests = EvalRequestRepository(database.sessionmaker)
    results = EvaluationResultRepository(database.sessionmaker)

    # Two results share a primary key, so the batch insert fails. Because both
    # writes share one transaction, the request row must roll back with them.
    duplicate = _new_result("req-atomic", "faithfulness")

    async def _write_with_conflict() -> None:
        async with requests.begin() as session:
            await requests.create(_new_request("req-atomic"), session=session)
            await results.create_many([duplicate, duplicate], session=session)

    with pytest.raises(IntegrityError):
        await _write_with_conflict()

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            request_count = conn.execute(
                text("SELECT count(*) FROM eval_requests WHERE id = 'req-atomic'")
            ).scalar()
    finally:
        engine.dispose()

    assert request_count == 0
