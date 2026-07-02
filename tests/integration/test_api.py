"""Integration tests for the evaluate API via httpx AsyncClient."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

_VALID_BODY = {
    "task_type": "summarization",
    "input_text": "Paris is the capital of France and its largest city.",
    "output_text": "Paris is France's capital.",
    "prompt": "Summarize the text.",
    "metadata": {"inference_id": "inf-1", "model_id": "mdl-1"},
}


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "arc-eval-service"


async def test_evaluate_returns_scores(stub_client: AsyncClient) -> None:
    response = await stub_client.post("/v1/evaluate", json=_VALID_BODY)

    assert response.status_code == 200
    results = response.json()["results"]
    assert {r["metric_name"] for r in results} == {"faithfulness", "answer_relevance"}
    assert all(r["evaluator_version"] == "v1" for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)


async def test_missing_required_field_is_422(client: AsyncClient) -> None:
    body = {"task_type": "summarization", "input_text": "x"}  # no output_text
    response = await client.post("/v1/evaluate", json=body)
    assert response.status_code == 422


async def test_evaluate_persists_request_and_results(
    stub_client: AsyncClient, clean_db: str
) -> None:
    await stub_client.post("/v1/evaluate", json=_VALID_BODY)

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            requests = conn.execute(
                text("SELECT inference_id, task_type FROM eval_requests")
            ).all()
            results = conn.execute(
                text("SELECT metric_name, error, inference_id FROM evaluation_results")
            ).all()
    finally:
        engine.dispose()

    assert [(r.inference_id, r.task_type) for r in requests] == [
        ("inf-1", "summarization")
    ]
    assert {r.metric_name for r in results} == {"faithfulness", "answer_relevance"}
    assert all(r.error is None for r in results)
    assert all(r.inference_id == "inf-1" for r in results)


async def test_no_judge_model_returns_no_scores_but_persists_errors(
    client: AsyncClient, clean_db: str
) -> None:
    # The default app has no model profile configured, so every metric errors.
    response = await client.post("/v1/evaluate", json=_VALID_BODY)

    assert response.status_code == 200
    assert response.json()["results"] == []

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            errored = conn.execute(
                text("SELECT error FROM evaluation_results WHERE error IS NOT NULL")
            ).all()
    finally:
        engine.dispose()

    # One errored row per summarization metric, kept for observability.
    assert len(errored) == 2
