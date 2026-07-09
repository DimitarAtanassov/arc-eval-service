from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from arc_eval_service.domain.errors import LabInferenceError, ModelNotFoundError

pytestmark = pytest.mark.integration

# The experiment_env fixture yields (client, fake_lab); the lab fake is typed Any
# here so a test can set fake_lab.error without importing the conftest-private type.
_Env = tuple[AsyncClient, Any]

_CREATE = {
    "name": "baseline",
    "model_name": "candidate",
    "generation_config": {"temperature": 0.0, "max_output_tokens": 64},
    "description": "first",
}


async def _create(client: AsyncClient, name: str = "baseline") -> str:
    response = await client.post("/v1/experiments", json={**_CREATE, "name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


async def test_create_and_get(experiment_env: _Env) -> None:
    client, _ = experiment_env
    exp_id = await _create(client)

    got = await client.get(f"/v1/experiments/{exp_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["name"] == "baseline"
    assert body["model_name"] == "candidate"
    assert body["generation_config"] == {"temperature": 0.0, "max_output_tokens": 64}


async def test_create_duplicate_name_is_409(experiment_env: _Env) -> None:
    client, _ = experiment_env
    await _create(client, "dup")
    response = await client.post("/v1/experiments", json={**_CREATE, "name": "dup"})
    assert response.status_code == 409


async def test_get_unknown_is_404(experiment_env: _Env) -> None:
    client, _ = experiment_env
    response = await client.get("/v1/experiments/missing")
    assert response.status_code == 404


async def test_list_experiments(experiment_env: _Env) -> None:
    client, _ = experiment_env
    await _create(client, "one")
    await _create(client, "two")
    response = await client.get("/v1/experiments", params={"limit": 10})
    assert response.status_code == 200
    assert {e["name"] for e in response.json()} == {"one", "two"}


async def test_run_with_metrics_scores_and_persists(
    experiment_env: _Env, clean_db: str
) -> None:
    client, _ = experiment_env
    exp_id = await _create(client)

    response = await client.post(
        f"/v1/experiments/{exp_id}/run",
        json={
            "input_text": "Paris is the capital of France.",
            "metrics": ["faithfulness"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["inference_id"] == "inf-1"
    assert body["experiment_id"] == exp_id
    assert {r["metric_name"] for r in body["evaluation"]["results"]} == {"faithfulness"}

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            runs = conn.execute(
                text("SELECT inference_id, eval_request_id FROM experiment_runs")
            ).all()
    finally:
        engine.dispose()
    assert runs[0].inference_id == "inf-1"
    assert runs[0].eval_request_id is not None


async def test_run_without_metrics_skips_evaluation(experiment_env: _Env) -> None:
    client, _ = experiment_env
    exp_id = await _create(client)
    response = await client.post(
        f"/v1/experiments/{exp_id}/run", json={"input_text": "text"}
    )
    assert response.status_code == 201
    assert response.json()["evaluation"] is None


async def test_run_unknown_experiment_is_404(experiment_env: _Env) -> None:
    client, _ = experiment_env
    response = await client.post(
        "/v1/experiments/missing/run", json={"input_text": "text"}
    )
    assert response.status_code == 404


async def test_run_lab_down_is_502(experiment_env: _Env) -> None:
    client, fake_lab = experiment_env
    fake_lab.error = LabInferenceError("lab down")
    exp_id = await _create(client)
    response = await client.post(
        f"/v1/experiments/{exp_id}/run", json={"input_text": "text"}
    )
    assert response.status_code == 502


async def test_run_unknown_model_is_404(experiment_env: _Env) -> None:
    client, fake_lab = experiment_env
    fake_lab.error = ModelNotFoundError("candidate")
    exp_id = await _create(client)
    response = await client.post(
        f"/v1/experiments/{exp_id}/run", json={"input_text": "text"}
    )
    assert response.status_code == 404


async def test_results_and_compare(experiment_env: _Env) -> None:
    client, _ = experiment_env
    exp_id = await _create(client)
    await client.post(
        f"/v1/experiments/{exp_id}/run",
        json={
            "input_text": "Paris is the capital of France.",
            "metrics": ["faithfulness"],
        },
    )

    results = await client.get(f"/v1/experiments/{exp_id}/results")
    assert results.status_code == 200
    assert "faithfulness" in {m["metric_name"] for m in results.json()["metrics"]}

    compare = await client.get(f"/v1/experiments/{exp_id}/compare/{exp_id}")
    assert compare.status_code == 200
    assert len(compare.json()["experiments"]) == 2


async def test_dependency_factory_builds_real_service(clean_db: str) -> None:
    from arc_eval_service.api.dependencies import (
        get_experiment_service,
        get_lab_inference_client,
    )
    from arc_eval_service.services.experiment_service import ExperimentService

    assert get_lab_inference_client() is None
    assert isinstance(get_experiment_service(), ExperimentService)
