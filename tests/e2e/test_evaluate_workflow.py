"""End-to-end evaluation workflow test.

Exercise the full vertical slice through the running ASGI app: receive one
completed interaction, score it, persist the request and its results, and confirm
the scores are returned and the rows link back to the caller's inference id.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.e2e


async def test_evaluate_then_read_back_the_results(
    stub_client: AsyncClient, clean_db: str
) -> None:
    body = {
        "task_type": "summarization",
        "input_text": "The Eiffel Tower is a landmark in Paris, France.",
        "output_text": "The Eiffel Tower is in Paris.",
        "prompt": "Summarize the text.",
        "metadata": {"inference_id": "inf-42", "model_id": "qwen-1.5b"},
    }

    response = await stub_client.post("/v1/evaluate", json=body)
    assert response.status_code == 200
    scored = response.json()["results"]
    assert {r["metric_name"] for r in scored} == {"faithfulness", "answer_relevance"}

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            request_row = conn.execute(
                text(
                    "SELECT id, inference_id, model_id, output_text FROM eval_requests"
                )
            ).one()
            result_rows = conn.execute(
                text(
                    "SELECT metric_name, score, evaluator_version, eval_request_id, "
                    "inference_id, judge, prompt FROM evaluation_results "
                    "ORDER BY metric_name"
                )
            ).all()
    finally:
        engine.dispose()

    assert request_row.inference_id == "inf-42"
    assert request_row.model_id == "qwen-1.5b"
    assert request_row.output_text == "The Eiffel Tower is in Paris."
    # Every result links back to the same request and the caller's inference id.
    assert {r.metric_name for r in result_rows} == {"answer_relevance", "faithfulness"}
    assert all(r.eval_request_id == request_row.id for r in result_rows)
    assert all(r.inference_id == "inf-42" for r in result_rows)
    assert all(r.evaluator_version == "v1" for r in result_rows)
    # Judge and prompt provenance are captured on every result.
    assert all(r.judge["name"] == "default" for r in result_rows)
    assert all(r.judge["model"] == "stub-judge" for r in result_rows)
    assert all(r.judge["system_prompt"] for r in result_rows)
    assert all(r.prompt["template"] for r in result_rows)
    assert all(
        r.prompt["variables"]["output"] == "The Eiffel Tower is in Paris."
        for r in result_rows
    )
