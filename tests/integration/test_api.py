"""Integration tests for the HTTP API via httpx AsyncClient."""

import pytest
from httpx import ASGITransport, AsyncClient

from arc_eval_service.api.main import create_app
from arc_eval_service.core.config import get_settings

pytestmark = pytest.mark.integration


async def test_health_ok(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "arc-eval-service"


async def test_list_evaluators(client: AsyncClient):
    response = await client.get("/v1/evaluators")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"exact_match", "regex", "latency", "token", "cost"} <= names


async def test_evaluate_sync_returns_completed_record(client: AsyncClient):
    payload = {
        "case": {"request_id": "req-1", "output": "hello", "reference": "hello"},
        "evaluators": [{"name": "exact_match", "config": {}}],
        "mode": "sync",
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["passed"] is True
    assert body["aggregate_score"] == 1.0
    assert body["results"][0]["evaluator_name"] == "exact_match"
    assert body["results"][0]["latency_ms"] >= 0.0


async def test_evaluate_multiple_evaluators_aggregates(client: AsyncClient):
    payload = {
        "case": {
            "request_id": "req-2",
            "output": "answer 42",
            "reference": "answer 42",
            "latency_ms": 50.0,
            "cost_usd": 0.001,
        },
        "evaluators": [
            {"name": "exact_match"},
            {"name": "latency", "config": {"threshold_ms": 100}},
            {"name": "cost", "config": {"max_cost_usd": 0.01}},
        ],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 3
    assert body["passed"] is True


async def test_evaluate_unknown_evaluator_is_400(client: AsyncClient):
    payload = {
        "case": {"request_id": "req-3", "output": "x"},
        "evaluators": [{"name": "nope"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


async def test_evaluate_requires_at_least_one_evaluator(client: AsyncClient):
    payload = {"case": {"request_id": "req-4", "output": "x"}, "evaluators": []}
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 422


async def test_get_unknown_evaluation_is_404(client: AsyncClient):
    response = await client.get("/v1/evaluations/missing-id")
    assert response.status_code == 404


async def test_batch_preserves_order(client: AsyncClient):
    payload = {
        "items": [
            {
                "case": {"request_id": "b1", "output": "a", "reference": "a"},
                "evaluators": [{"name": "exact_match"}],
            },
            {
                "case": {"request_id": "b2", "output": "a", "reference": "b"},
                "evaluators": [{"name": "exact_match"}],
            },
        ]
    }
    response = await client.post("/v1/evaluate/batch", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert [r["request_id"] for r in body] == ["b1", "b2"]
    assert body[0]["passed"] is True
    assert body[1]["passed"] is False


async def test_batch_over_max_batch_size_is_413(monkeypatch):
    monkeypatch.setenv("ARC_EVAL_MAX_BATCH_SIZE", "1")
    get_settings.cache_clear()
    item = {
        "case": {"request_id": "b", "output": "a", "reference": "a"},
        "evaluators": [{"name": "exact_match"}],
    }
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/evaluate/batch", json={"items": [item, item]})
    assert response.status_code == 413
    assert "max_batch_size" in response.json()["detail"]


async def test_lifespan_disposes_store_on_shutdown():
    app = create_app()
    async with app.router.lifespan_context(app):
        pass  # exiting the context triggers shutdown -> store.dispose()


async def test_evaluator_error_is_captured_not_fatal(client: AsyncClient):
    # exact_match without a reference -> per-evaluator error, request still 200.
    payload = {
        "case": {"request_id": "req-5", "output": "x"},
        "evaluators": [{"name": "exact_match"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["results"][0]["error"] is not None
