"""End-to-end evaluation workflow tests.

Exercise the full vertical slice through the running ASGI app (on a stub judge
model): submit -> execute -> retrieve, for sync and async modes, plus re-run.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_async_submit_then_poll_completes(client: AsyncClient) -> None:
    payload = {
        "case": {
            "request_id": "e2e-async",
            "input": "What is the capital of France?",
            "output": "Paris",
            "context": ["France's capital is Paris."],
        },
        "judges": [
            {"judge": "safety"},
            {"judge": "answer_relevance"},
            {"judge": "faithfulness"},
        ],
        "mode": "async",
    }

    submit = await client.post("/v1/evaluate", json=payload)
    assert submit.status_code == 200
    submitted = submit.json()
    assert submitted["status"] == "pending"
    evaluation_id = submitted["evaluation_id"]

    # BackgroundTasks complete before the next in-process request is handled.
    record = (await client.get(f"/v1/evaluations/{evaluation_id}")).json()
    assert record["status"] == "completed"
    assert record["passed"] is True
    assert len(record["results"]) == 3
    assert record["completed_at"] is not None


async def test_sync_workflow_retrievable_afterwards(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "e2e-sync", "output": "hi"},
        "judges": [{"judge": "safety"}],
        "mode": "sync",
    }
    created = await client.post("/v1/evaluate", json=payload)
    evaluation_id = created.json()["evaluation_id"]

    fetched = await client.get(f"/v1/evaluations/{evaluation_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"


async def test_rerun_workflow_links_and_completes(client: AsyncClient) -> None:
    payload = {
        "case": {"request_id": "e2e-rerun", "output": "hi"},
        "judges": [{"judge": "safety"}],
    }
    original = (await client.post("/v1/evaluate", json=payload)).json()

    # Re-run with a different judge on the stored case.
    rerun = await client.post(
        f"/v1/evaluations/{original['evaluation_id']}/rerun",
        json={"judges": [{"judge": "custom", "config": {"prompt": "grade tone"}}]},
    )
    body = rerun.json()
    assert body["status"] == "completed"
    assert body["rerun_of"] == original["evaluation_id"]
    assert body["results"][0]["judge"] == "custom"
