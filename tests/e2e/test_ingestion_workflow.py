"""End-to-end ingestion workflow tests.

Exercise the full vertical slice through the running ASGI app: receive one LLM
interaction, store the eval input, and confirm it persists and reads back.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_store_then_read_back_the_interaction(
    client: AsyncClient, clean_db: str
) -> None:
    payload = {
        "rendered_prompt": "Q: What is the capital of France?\nContext: The capital of France is Paris.",
        "system_message": "You are a careful assistant.",
        "model_response": {"role": "assistant", "content": "Paris."},
        "model_config": {"model": "gpt-4o", "temperature": 0.0},
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

    assert stored.system_message == "You are a careful assistant."
    assert stored.response["content"] == "Paris."
    assert stored.config["model"] == "gpt-4o"
