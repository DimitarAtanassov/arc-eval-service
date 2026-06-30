"""Integration tests for the ingestion API via httpx AsyncClient."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "arc-eval-service"


async def test_create_eval_input_returns_ids(client: AsyncClient) -> None:
    payload = {
        "prompt_template": "Answer the question: {question}",
        "template_context": {"question": "What is the capital of France?"},
        "rendered_prompt": "Answer the question: What is the capital of France?",
        "system_message": "Be concise.",
        "llm_response": {"role": "assistant", "content": "Paris."},
        "llm_config": {"model": "gpt-4o", "temperature": 0.0},
    }
    response = await client.post("/v1/eval-inputs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["eval_input_id"]
    assert body["prompt_template_id"]


async def test_identical_templates_share_one_row(client: AsyncClient) -> None:
    base = {
        "prompt_template": "Grade: {x}",
        "rendered_prompt": "Grade: 1",
        "llm_response": {"content": "ok"},
    }
    first = (
        await client.post(
            "/v1/eval-inputs", json={**base, "template_context": {"x": "1"}}
        )
    ).json()
    second = (
        await client.post(
            "/v1/eval-inputs",
            json={
                **base,
                "template_context": {"x": "2"},
                "rendered_prompt": "Grade: 2",
            },
        )
    ).json()
    assert first["prompt_template_id"] == second["prompt_template_id"]
    assert first["eval_input_id"] != second["eval_input_id"]


async def test_different_templates_get_distinct_rows(client: AsyncClient) -> None:
    one = (
        await client.post(
            "/v1/eval-inputs",
            json={
                "prompt_template": "Template A: {x}",
                "rendered_prompt": "Template A: 1",
                "llm_response": {"content": "ok"},
            },
        )
    ).json()
    two = (
        await client.post(
            "/v1/eval-inputs",
            json={
                "prompt_template": "Template B: {x}",
                "rendered_prompt": "Template B: 1",
                "llm_response": {"content": "ok"},
            },
        )
    ).json()
    assert one["prompt_template_id"] != two["prompt_template_id"]


async def test_missing_required_fields_is_422(client: AsyncClient) -> None:
    response = await client.post("/v1/eval-inputs", json={"prompt_template": "x"})
    assert response.status_code == 422


async def test_stored_input_round_trips_through_the_database(
    client: AsyncClient, clean_db: str
) -> None:
    payload = {
        "prompt_template": "P: {a}",
        "template_context": {"a": "hi"},
        "rendered_prompt": "P: hi",
        "llm_response": {"content": "yo"},
        "llm_config": {"model": "m"},
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

    assert stored.prompt_template_id == created["prompt_template_id"]
    assert stored.rendered_prompt == "P: hi"
    assert stored.template_context == {"a": "hi"}
    assert stored.llm_response == {"content": "yo"}
    assert stored.llm_config == {"model": "m"}
