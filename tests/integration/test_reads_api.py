"""Integration tests for the read (browse) endpoints via httpx AsyncClient.

The write path (``POST /v1/evaluate``) seeds the database through ``stub_client``;
the read endpoints then run over the real read service, repositories and catalog,
so browse projections and the read queries are exercised end to end.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

_BODY = {
    "input_text": "Paris is the capital of France and its largest city.",
    "output_text": "Paris is France's capital.",
    "prompt": "Summarize the text.",
    "metrics": ["faithfulness", "answer_relevance"],
    "metadata": {"inference_id": "inf-1", "model_id": "mdl-1"},
}


async def _seed(client: AsyncClient, **overrides: object) -> None:
    response = await client.post("/v1/evaluate", json={**_BODY, **overrides})
    assert response.status_code == 200


async def test_list_metrics_returns_the_catalog(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/v1/metrics")

    assert response.status_code == 200
    assert {m["name"] for m in response.json()} == {
        "faithfulness",
        "answer_relevance",
        "safety",
    }


async def test_list_metrics_projects_definition_fields(
    stub_client: AsyncClient,
) -> None:
    response = await stub_client.get("/v1/metrics")

    by_name = {m["name"]: m for m in response.json()}
    assert by_name["faithfulness"]["requires"] == ["output", "context"]
    assert by_name["safety"]["threshold"] == 0.8
    assert by_name["faithfulness"]["rubric"]
    assert by_name["faithfulness"]["version"]


async def test_list_requests_returns_the_seeded_interaction(
    stub_client: AsyncClient,
) -> None:
    await _seed(stub_client)

    response = await stub_client.get("/v1/requests")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["inference_id"] == "inf-1"
    assert rows[0]["model_id"] == "mdl-1"
    assert rows[0]["output_preview"] == "Paris is France's capital."


async def test_request_preview_collapses_and_truncates_long_text(
    stub_client: AsyncClient,
) -> None:
    await _seed(stub_client, input_text="x" * 300, output_text="one  two   three")

    rows = (await stub_client.get("/v1/requests")).json()

    # Long input is truncated to a single-line, ellipsis-terminated preview...
    assert rows[0]["input_preview"].endswith("\u2026")
    assert len(rows[0]["input_preview"]) == 160
    # ...while short text is returned with its whitespace collapsed.
    assert rows[0]["output_preview"] == "one two three"


async def test_get_request_detail_includes_every_metric_score(
    stub_client: AsyncClient,
) -> None:
    await _seed(stub_client)
    request_id = (await stub_client.get("/v1/requests")).json()[0]["id"]

    response = await stub_client.get(f"/v1/requests/{request_id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == request_id
    assert detail["input_text"] == _BODY["input_text"]
    assert detail["metadata"]["inference_id"] == "inf-1"
    assert {r["metric_name"] for r in detail["results"]} == {
        "faithfulness",
        "answer_relevance",
    }


async def test_get_request_detail_is_404_for_unknown_id(
    stub_client: AsyncClient,
) -> None:
    response = await stub_client.get("/v1/requests/does-not-exist")

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


async def test_list_results_returns_the_persisted_scores(
    stub_client: AsyncClient,
) -> None:
    await _seed(stub_client)

    response = await stub_client.get("/v1/results")

    assert response.status_code == 200
    rows = response.json()
    assert {r["metric_name"] for r in rows} == {"faithfulness", "answer_relevance"}
    assert all(r["model_id"] == "mdl-1" for r in rows)


async def test_list_results_filters_by_metric(stub_client: AsyncClient) -> None:
    await _seed(stub_client)

    rows = (
        await stub_client.get("/v1/results", params={"metric": "faithfulness"})
    ).json()

    assert {r["metric_name"] for r in rows} == {"faithfulness"}


async def test_list_results_filters_by_model_id(stub_client: AsyncClient) -> None:
    await _seed(stub_client)

    matched = (
        await stub_client.get("/v1/results", params={"model_id": "mdl-1"})
    ).json()
    absent = (await stub_client.get("/v1/results", params={"model_id": "other"})).json()

    assert len(matched) == 2
    assert absent == []
