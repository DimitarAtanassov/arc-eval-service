"""Integration test: POST /v1/evaluate resolving the interaction by inference_id.

The lab read is faked (no network); the real coordinator, resolver, scoring
service, repositories, and database run, so the id path is proven end to end
through the ASGI app, down to the persisted rows.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from arc_eval_service.clients.lab_inference_client import InferenceResult

pytestmark = pytest.mark.integration


class _FakeReader:
    """A stand-in InferenceReader that returns a canned inference (no network)."""

    def __init__(self, result: InferenceResult) -> None:
        self._result = result
        self.calls: list[str] = []

    async def get_inference(
        self, inference_id: str, *, correlation_id: str | None = None
    ) -> InferenceResult:
        self.calls.append(inference_id)
        return self._result


def _inference() -> InferenceResult:
    return InferenceResult(
        id="inf-77",
        model_id="mdl-77",
        input_text="Paris is the capital of France.",
        prompt="Summarize the text.",
        output_text="Paris is the capital.",
        latency_ms=10,
        prompt_tokens=5,
        completion_tokens=2,
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
    )


async def test_evaluate_by_inference_id_resolves_scores_and_persists(
    stub_app: FastAPI, clean_db: str
) -> None:
    from arc_eval_service.api.dependencies import get_interaction_resolver
    from arc_eval_service.services.interaction_resolver import InteractionResolver

    reader = _FakeReader(_inference())
    stub_app.dependency_overrides[get_interaction_resolver] = lambda: (
        InteractionResolver(reader)
    )

    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/evaluate",
            json={"inference_id": "inf-77", "metrics": ["faithfulness"]},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert {r["metric_name"] for r in results} == {"faithfulness"}
    assert reader.calls == ["inf-77"]

    engine = create_engine(clean_db)
    try:
        with engine.connect() as conn:
            requests = conn.execute(
                text("SELECT input_text, inference_id FROM eval_requests")
            ).all()
            scores = conn.execute(
                text("SELECT inference_id FROM evaluation_results")
            ).all()
    finally:
        engine.dispose()

    # The fetched inference's text and id were persisted, proving resolution wired
    # the lab's response through scoring into storage.
    assert [r.input_text for r in requests] == ["Paris is the capital of France."]
    assert [r.inference_id for r in requests] == ["inf-77"]
    assert all(s.inference_id == "inf-77" for s in scores)
