"""End-to-end evaluation workflow tests.

Exercise the full vertical slice through the running ASGI app: submit -> execute
-> retrieve, for both async and sync execution modes.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_async_submit_then_poll_completes(client: AsyncClient):
    payload = {
        "case": {
            "request_id": "e2e-async",
            "output": "the answer is 42",
            "reference": "the answer is 42",
            "latency_ms": 120.0,
            "prompt_tokens": 8,
            "completion_tokens": 12,
            "cost_usd": 0.002,
        },
        "evaluators": [
            {"name": "exact_match"},
            {"name": "regex", "config": {"pattern": r"42"}},
            {"name": "latency", "config": {"threshold_ms": 500}},
            {"name": "token", "config": {"max_total_tokens": 100}},
            {"name": "cost", "config": {"max_cost_usd": 0.01}},
        ],
        "mode": "async",
    }

    submit = await client.post("/v1/evaluate", json=payload)
    assert submit.status_code == 200
    submitted = submit.json()
    assert submitted["status"] == "pending"
    assert submitted["mode"] == "async"
    evaluation_id = submitted["evaluation_id"]

    # BackgroundTasks run after the response is sent; with the in-process ASGI
    # transport the task has completed by the time the next request is handled.
    fetched = await client.get(f"/v1/evaluations/{evaluation_id}")
    assert fetched.status_code == 200
    record = fetched.json()
    assert record["status"] == "completed"
    assert record["passed"] is True
    assert record["aggregate_score"] == 1.0
    assert len(record["results"]) == 5
    assert record["completed_at"] is not None


async def test_sync_workflow_retrievable_afterwards(client: AsyncClient):
    payload = {
        "case": {"request_id": "e2e-sync", "output": "hi", "reference": "hi"},
        "evaluators": [{"name": "exact_match"}],
        "mode": "sync",
    }

    created = await client.post("/v1/evaluate", json=payload)
    assert created.status_code == 200
    evaluation_id = created.json()["evaluation_id"]

    fetched = await client.get(f"/v1/evaluations/{evaluation_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"


async def test_regression_scoring_detects_drop(client: AsyncClient):
    """A regression shows up as a failing evaluator and a lower aggregate."""
    baseline = {
        "case": {"request_id": "base", "output": "correct", "reference": "correct"},
        "evaluators": [{"name": "exact_match"}],
    }
    candidate = {
        "case": {"request_id": "cand", "output": "wrong", "reference": "correct"},
        "evaluators": [{"name": "exact_match"}],
    }

    base_resp = await client.post("/v1/evaluate", json=baseline)
    cand_resp = await client.post("/v1/evaluate", json=candidate)

    assert base_resp.json()["aggregate_score"] == 1.0
    assert cand_resp.json()["aggregate_score"] == 0.0
    assert base_resp.json()["passed"] is True
    assert cand_resp.json()["passed"] is False
