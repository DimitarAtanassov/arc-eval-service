"""Integration tests for the HTTP API via httpx AsyncClient (stub judge model)."""

import gzip
import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "arc-eval-service"


async def test_list_metrics(client: AsyncClient) -> None:
    response = await client.get("/v1/metrics")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert names == {"faithfulness", "answer_relevance", "safety", "custom"}


async def test_list_models_exposes_profiles(client: AsyncClient) -> None:
    response = await client.get("/v1/models")
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"default"}


async def test_evaluate_returns_per_metric_results(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "req-1", "output": "hello"},
        "metrics": [{"metric": "safety"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-1" and body["case_id"]
    assert "aggregate_score" not in body
    result = body["results"][0]
    assert result["metric"] == "safety"
    assert result["passed"] is True
    assert result["label"] == "pass"
    assert result["explanation"]


async def test_evaluate_unknown_metric_is_400(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "r", "output": "x"},
        "metrics": [{"metric": "nope"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


async def test_evaluate_unknown_model_is_400(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "r", "output": "x"},
        "metrics": [{"metric": "safety", "model": "ghost"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 400
    assert "ghost" in response.json()["detail"]


async def test_evaluate_requires_at_least_one_metric(client: AsyncClient) -> None:
    payload = {"case": {"request_id": "r", "output": "x"}, "metrics": []}
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 422


async def test_missing_required_field_degrades_not_fatal(client: AsyncClient) -> None:
    # faithfulness requires context; absent -> per-metric error, request still 200.
    payload = {
        "case": {"request_id": "r5", "output": "x"},
        "metrics": [{"metric": "faithfulness"}],
    }
    response = await client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    assert response.json()["results"][0]["error"] is not None


async def test_rerun_with_override_replaces_metrics(client: AsyncClient) -> None:
    created = (
        await client.post(
            "/v1/evaluate",
            json={
                "case": {"request_id": "rr", "output": "hello"},
                "metrics": [{"metric": "safety"}],
            },
        )
    ).json()
    rerun = await client.post(
        f"/v1/evaluations/{created['case_id']}/rerun",
        json={"metrics": [{"metric": "custom", "config": {"prompt": "grade tone"}}]},
    )
    assert rerun.status_code == 200
    body = rerun.json()
    assert body["case_id"] == created["case_id"]
    assert body["results"][0]["metric"] == "custom"


async def test_batch_scores_each_item(client: AsyncClient) -> None:
    payload = {
        "items": [
            {
                "case": {"request_id": "b1", "output": "x"},
                "metrics": [{"metric": "safety"}],
            },
            {
                "case": {"request_id": "b2", "output": "y"},
                "metrics": [{"metric": "safety"}],
            },
        ]
    }
    response = await client.post("/v1/evaluate/batch", json=payload)
    assert response.status_code == 200
    assert {r["request_id"] for r in response.json()} == {"b1", "b2"}


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
                                "spanId": "s1",
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


async def test_otlp_ingest_accepts_gzip_encoded_body(client: AsyncClient) -> None:
    # The collector's otlphttp exporter gzip-compresses by default; the receiver
    # must decode it (without the middleware this returns 400).
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "arc.llm.call",
                                "traceId": "gz-trace",
                                "spanId": "gz-span",
                                "events": [
                                    {
                                        "name": "arc.llm.choice",
                                        "attributes": [
                                            {
                                                "key": "arc.llm.message.content",
                                                "value": {"stringValue": "hi"},
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
    body = gzip.compress(json.dumps(payload).encode())
    response = await client.post(
        "/v1/otlp/traces",
        content=body,
        headers={"content-type": "application/json", "content-encoding": "gzip"},
    )
    assert response.status_code == 202
    assert response.json()["accepted"] == 1


async def test_otlp_ingest_stores_spans_and_serves_real_trace(
    client: AsyncClient,
) -> None:
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "arc-gateway"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "arc.llm.call",
                                "traceId": "trace-real",
                                "spanId": "span-root",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1500000000",
                                "attributes": [
                                    {
                                        "key": "arc.request_id",
                                        "value": {"stringValue": "req-real"},
                                    },
                                    {
                                        "key": "arc.llm.request.model",
                                        "value": {"stringValue": "gpt-4o"},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    ingest = await client.post("/v1/otlp/traces", json=payload)
    assert ingest.status_code == 202
    assert ingest.json()["spans"] == 1

    trace = await client.get("/v1/traces/trace-real")
    assert trace.status_code == 200
    body = trace.json()
    assert body["trace_id"] == "trace-real"
    assert body["request_id"] == "req-real"
    span = body["spans"][0]
    assert span["span_id"] == "span-root"
    assert span["parent_span_id"] is None
    assert span["duration_ms"] == 500.0
    assert span["attributes"]["arc.llm.request.model"] == "gpt-4o"


async def test_get_unknown_trace_is_404(client: AsyncClient) -> None:
    assert (await client.get("/v1/traces/missing-trace")).status_code == 404


async def test_get_unknown_evaluation_is_404(client: AsyncClient) -> None:
    assert (await client.get("/v1/evaluations/missing-id")).status_code == 404


async def test_list_then_delete_evaluation(client: AsyncClient) -> None:
    created = (
        await client.post(
            "/v1/evaluate",
            json={
                "case": {"request_id": "del", "output": "a"},
                "metrics": [{"metric": "safety"}],
            },
        )
    ).json()
    listed = await client.get("/v1/evaluations?limit=10")
    assert listed.status_code == 200
    assert created["case_id"] in {item["case_id"] for item in listed.json()}

    deleted = await client.delete(f"/v1/evaluations/{created['case_id']}")
    assert deleted.status_code == 204
    assert (
        await client.get(f"/v1/evaluations/{created['case_id']}")
    ).status_code == 404
