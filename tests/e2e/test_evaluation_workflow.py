"""End-to-end evaluation workflow tests (stub judge model).

Exercise the full vertical slice through the running ASGI app: evaluate -> store
-> retrieve, plus re-run on a stored case.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_sync_workflow_retrievable_afterwards(client: AsyncClient) -> None:
    payload = {
        "case": {
            "request_id": "e2e-sync",
            "input": "What is the capital of France?",
            "output": "Paris",
            "context": ["France's capital is Paris."],
        },
        "metrics": [
            {"metric": "safety"},
            {"metric": "answer_relevance"},
            {"metric": "faithfulness"},
        ],
    }
    created = (await client.post("/v1/evaluate", json=payload)).json()
    case_id = created["case_id"]
    assert len(created["results"]) == 3

    fetched = await client.get(f"/v1/evaluations/{case_id}")
    assert fetched.status_code == 200
    assert len(fetched.json()["results"]) == 3


async def test_rerun_replaces_results_on_the_case(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "e2e-rerun", "output": "hi"},
        "metrics": [{"metric": "safety"}],
    }
    original = (await client.post("/v1/evaluate", json=payload)).json()

    rerun = await client.post(
        f"/v1/evaluations/{original['case_id']}/rerun",
        json={"metrics": [{"metric": "custom", "config": {"prompt": "grade tone"}}]},
    )
    assert rerun.status_code == 200
    assert rerun.json()["results"][0]["metric"] == "custom"

    fetched = (await client.get(f"/v1/evaluations/{original['case_id']}")).json()
    assert {r["metric"] for r in fetched["results"]} == {"custom"}
