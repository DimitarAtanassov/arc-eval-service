"""Integration tests for the experiments API (dataset evaluator).

Uses the ``experiment_client`` fixture: the real experiment repositories, dataset
store, scoring, and database run against a stub judge, so create -> add dataset ->
run -> score -> persist -> aggregate is exercised without a network call.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _create(
    client: AsyncClient,
    *,
    name: str = "exp",
    metrics: list[str] | None = None,
    dataset: list[dict[str, str]] | None = None,
) -> dict:
    body: dict[str, object] = {"name": name, "metrics": metrics or ["faithfulness"]}
    if dataset is not None:
        body["dataset"] = dataset
    response = await client.post("/v1/experiments", json=body)
    return {"status": response.status_code, "body": response.json()}


async def test_create_with_dataset_returns_size(experiment_client: AsyncClient) -> None:
    result = await _create(
        experiment_client, dataset=[{"input_text": "a", "output_text": "b"}]
    )

    assert result["status"] == 201
    assert result["body"]["metrics"] == ["faithfulness"]
    assert result["body"]["dataset_size"] == 1


async def test_create_unknown_metric_is_404(experiment_client: AsyncClient) -> None:
    result = await _create(experiment_client, metrics=["not-a-metric"])
    assert result["status"] == 404


async def test_create_duplicate_name_is_409(experiment_client: AsyncClient) -> None:
    await _create(experiment_client, name="dup")
    result = await _create(experiment_client, name="dup")
    assert result["status"] == 409


async def test_add_dataset_appends(experiment_client: AsyncClient) -> None:
    created = (await _create(experiment_client))["body"]

    response = await experiment_client.post(
        f"/v1/experiments/{created['id']}/dataset",
        json={
            "entries": [
                {"input_text": "a", "output_text": "b"},
                {"input_text": "c", "output_text": "d", "system_text": "be precise"},
            ]
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "experiment_id": created["id"],
        "added": 2,
        "dataset_size": 2,
    }


async def test_run_empty_dataset_is_409(experiment_client: AsyncClient) -> None:
    created = (await _create(experiment_client))["body"]
    response = await experiment_client.post(f"/v1/experiments/{created['id']}/run")
    assert response.status_code == 409


async def test_run_scores_the_dataset(experiment_client: AsyncClient) -> None:
    created = (
        await _create(
            experiment_client,
            metrics=["faithfulness", "answer_relevance"],
            dataset=[
                {
                    "input_text": "Paris is the capital of France.",
                    "output_text": "Paris is France's capital.",
                },
                {"input_text": "The sky is blue.", "output_text": "The sky is blue."},
            ],
        )
    )["body"]

    response = await experiment_client.post(f"/v1/experiments/{created['id']}/run")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["dataset_size"] == 2
    assert body["scored_count"] == 2
    scores = {m["metric_name"]: m for m in body["results"]}
    # The stub judge returns 0.9 for every metric.
    assert scores["faithfulness"]["average_score"] == pytest.approx(0.9)
    assert scores["faithfulness"]["evaluated_count"] == 2

    results = (
        await experiment_client.get(f"/v1/experiments/{created['id']}/results")
    ).json()
    result_scores = {m["metric_name"]: m for m in results["metrics"]}
    assert result_scores["faithfulness"]["average_score"] == pytest.approx(0.9)


async def test_list_and_get_expose_dataset_size(
    experiment_client: AsyncClient,
) -> None:
    created = (
        await _create(
            experiment_client,
            name="withdata",
            dataset=[{"input_text": "a", "output_text": "b"}],
        )
    )["body"]

    got = (await experiment_client.get(f"/v1/experiments/{created['id']}")).json()
    assert got["dataset_size"] == 1

    listing = (await experiment_client.get("/v1/experiments")).json()
    sizes = {experiment["id"]: experiment["dataset_size"] for experiment in listing}
    assert sizes[created["id"]] == 1


async def test_list_dataset_returns_entries_in_order(
    experiment_client: AsyncClient,
) -> None:
    created = (
        await _create(
            experiment_client,
            dataset=[
                {"input_text": "first", "output_text": "1"},
                {"input_text": "second", "output_text": "2"},
            ],
        )
    )["body"]

    entries = (
        await experiment_client.get(f"/v1/experiments/{created['id']}/dataset")
    ).json()

    assert [e["position"] for e in entries] == [0, 1]
    assert [e["input_text"] for e in entries] == ["first", "second"]
