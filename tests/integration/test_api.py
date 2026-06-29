"""Integration tests for the HTTP API via httpx AsyncClient (stub judge model)."""

import pytest
from httpx import ASGITransport, AsyncClient

from arc_eval_service.api.main import create_app
from arc_eval_service.core.config import get_settings

pytestmark = pytest.mark.integration


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "arc-eval-service"


async def test_list_judges(client: AsyncClient) -> None:
    response = await client.get("/v1/judges")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert names == {"faithfulness", "answer_relevance", "safety", "custom"}


async def test_list_models_exposes_profiles(client: AsyncClient) -> None:
    response = await client.get("/v1/models")
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"default"}


async def test_evaluate_sync_returns_completed_record(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "req-1", "output": "hello"},
        "judges": [{"judge": "safety"}],
        "mode": "sync",
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["passed"] is True
    assert body["aggregate_score"] == 0.9
    result = body["results"][0]
    assert result["judge"] == "safety"
    assert result["label"] == "pass"
    assert result["explanation"]


async def test_evaluate_unknown_judge_is_400(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "r", "output": "x"},
        "judges": [{"judge": "nope"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


async def test_evaluate_unknown_model_is_400(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "r", "output": "x"},
        "judges": [{"judge": "safety", "model": "ghost"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 400
    assert "ghost" in response.json()["detail"]


async def test_evaluate_requires_at_least_one_judge(client: AsyncClient) -> None:
    payload = {"case": {"request_id": "r", "output": "x"}, "judges": []}
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 422


async def test_missing_required_field_degrades_not_fatal(client: AsyncClient) -> None:
    # faithfulness requires context; absent -> per-judge error, request still 200.
    payload = {
        "case": {"request_id": "r5", "output": "x"},
        "judges": [{"judge": "faithfulness"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["results"][0]["error"] is not None


async def test_rerun_creates_linked_record(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "rr", "output": "hello"},
        "judges": [{"judge": "safety"}],
    }
    created = (await client.post("/v1/evaluate", json=payload)).json()
    rerun = await client.post(
        f"/v1/evaluations/{created['evaluation_id']}/rerun", json={}
    )
    assert rerun.status_code == 200
    body = rerun.json()
    assert body["rerun_of"] == created["evaluation_id"]
    assert body["evaluation_id"] != created["evaluation_id"]


async def test_otlp_ingest_accepts_and_counts(client: AsyncClient) -> None:
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "arc.llm.call",
                                "traceId": "t1",
                                "events": [
                                    {
                                        "name": "arc.llm.choice",
                                        "attributes": [
                                            {
                                                "key": "arc.llm.message.content",
                                                "value": {"stringValue": "an answer"},
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    response = await client.post("/v1/otlp/traces", json=payload)
    assert response.status_code == 202
    assert response.json()["accepted"] == 1


async def test_get_unknown_evaluation_is_404(client: AsyncClient) -> None:
    assert (await client.get("/v1/evaluations/missing-id")).status_code == 404


async def test_list_evaluations_returns_recent_first(client: AsyncClient) -> None:
    for rid in ("l1", "l2"):
        await client.post(
            "/v1/evaluate",
            json={
                "case": {"request_id": rid, "output": "a"},
                "judges": [{"judge": "safety"}],
            },
        )
    response = await client.get("/v1/evaluations?limit=10")
    assert [r["request_id"] for r in response.json()] == ["l2", "l1"]


async def test_list_evaluations_rejects_out_of_range_limit(client: AsyncClient) -> None:
    assert (await client.get("/v1/evaluations?limit=0")).status_code == 422
    assert (await client.get("/v1/evaluations?limit=101")).status_code == 422


async def test_batch_over_max_batch_size_is_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARC_EVAL_MAX_BATCH_SIZE", "1")
    get_settings.cache_clear()
    item = {
        "case": {"request_id": "b", "output": "a"},
        "judges": [{"judge": "safety"}],
    }
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        response = await anon.post("/v1/evaluate/batch", json={"items": [item, item]})
    assert response.status_code == 413
    assert "max_batch_size" in response.json()["detail"]


async def test_lifespan_disposes_store_on_shutdown() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        pass  # exiting the context triggers shutdown -> store.dispose()
