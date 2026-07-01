"""Integration tests for the ingestion API via httpx AsyncClient."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "arc-eval-service"


async def test_create_eval_input_returns_id(client: AsyncClient) -> None:
    payload = {
        "rendered_prompt": "Answer the question: What is the capital of France?",
        "system_message": "Be concise.",
        "model_response": {"role": "assistant", "content": "Paris."},
        "model_config": {"model": "gpt-4o", "temperature": 0.0},
    }
    response = await client.post("/v1/eval-inputs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["eval_input_id"]


async def test_missing_required_fields_is_422(client: AsyncClient) -> None:
    response = await client.post("/v1/eval-inputs", json={"rendered_prompt": "x"})
    assert response.status_code == 422


async def test_stored_input_round_trips_through_the_database(
    client: AsyncClient, clean_db: str
) -> None:
    payload = {
        "rendered_prompt": "P: hi",
        "model_response": {"content": "yo"},
        "model_config": {"model": "m"},
    }
    created = (await client.post("/v1/eval-inputs", json=payload)).json()

    from arc_eval_service.db.engine import Database
    from arc_eval_service.db.repositories import EvalInputRepository

    db = Database(clean_db)
    try:
        stored = await EvalInputRepository(db.sessionmaker).get(
            created["eval_input_id"]
        )
    finally:
        await db.dispose()

    assert stored.rendered_prompt == "P: hi"
    assert stored.response == {"content": "yo"}
    assert stored.config == {"model": "m"}
