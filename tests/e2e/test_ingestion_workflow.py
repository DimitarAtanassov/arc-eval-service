"""End-to-end ingestion workflow tests.

Exercise the full vertical slice through the running ASGI app: receive one LLM
interaction, store the template and the eval input, and confirm both persist and
link together.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_store_then_read_back_the_interaction(
    client: AsyncClient, clean_db: str
) -> None:
    payload = {
        "prompt_template": "Q: {question}\nContext: {context}",
        "template_context": {
            "question": "What is the capital of France?",
            "context": "The capital of France is Paris.",
        },
        "rendered_prompt": "Q: What is the capital of France?\nContext: The capital of France is Paris.",
        "system_message": "You are a careful assistant.",
        "llm_response": {"role": "assistant", "content": "Paris."},
        "llm_config": {"model": "gpt-4o", "temperature": 0.0},
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
    assert stored.system_message == "You are a careful assistant."
    assert stored.llm_response["content"] == "Paris."
    assert stored.template_context["question"] == "What is the capital of France?"
