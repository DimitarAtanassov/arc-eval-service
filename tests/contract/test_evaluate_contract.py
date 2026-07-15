"""Contract tests: the ``POST /v1/evaluate`` request and response wire shapes.

These lock the contract that arc-model-lab depends on. If a field is renamed,
added, or removed, they fail -- independent of any database or judge model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.api.schemas import (
    CONTRACT_VERSION,
    EvaluateRequest,
    EvaluateResponse,
)
from arc_eval_service.catalog import load_catalog
from arc_eval_service.db.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.services.evaluation_coordinator import EvaluationCoordinator
from arc_eval_service.services.evaluation_service import EvaluationService
from arc_eval_service.services.interaction_resolver import InteractionResolver

pytestmark = pytest.mark.contract

# The exact request body arc-model-lab sends after inference.
REQUEST_BODY = {
    "input_text": "the source article",
    "output_text": "the summary",
    "prompt": "Summarize the article.",
    "metrics": ["faithfulness", "answer_relevance"],
    "metadata": {"inference_id": "inf-1", "model_id": "mdl-1"},
}


class _FakeEngine(JudgeEngine):
    """Scores every metric with a fixed passing verdict; no model, no database."""

    def __init__(self) -> None:
        pass

    async def score(
        self,
        metric: str,
        case: EvaluationCase,
        *,
        case_id: str,
        judge: str | None = None,
    ) -> MetricScore:
        return MetricScore(
            metric=metric,
            model="stub",
            score=0.91,
            passed=True,
            label="pass",
            explanation="grounded in the source",
            latency_ms=1.0,
        )


class _NoopRequestRepo(EvalRequestRepository):
    def __init__(self) -> None:
        pass

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, None)

    async def create(
        self, item: NewEvalRequest, *, session: AsyncSession | None = None
    ) -> None:
        return None


class _NoopResultRepo(EvaluationResultRepository):
    def __init__(self) -> None:
        pass

    async def create_many(
        self,
        items: Sequence[NewEvaluationResult],
        *,
        session: AsyncSession | None = None,
    ) -> None:
        return None


def _service() -> EvaluationService:
    return EvaluationService(
        engine=_FakeEngine(),
        library=load_catalog(),
        requests=_NoopRequestRepo(),
        results=_NoopResultRepo(),
    )


def _coordinator() -> EvaluationCoordinator:
    # The wire entry point: an inline request needs no lab, so the resolver's reader
    # is None.
    return EvaluationCoordinator(
        resolver=InteractionResolver(None), evaluation=_service()
    )


def test_request_body_matches_the_contract() -> None:
    request = EvaluateRequest.model_validate(REQUEST_BODY)

    assert request.input_text == "the source article"
    assert request.output_text == "the summary"
    assert request.prompt == "Summarize the article."
    assert request.metrics == ["faithfulness", "answer_relevance"]
    assert request.metadata.inference_id == "inf-1"
    assert request.metadata.model_id == "mdl-1"


def test_request_requires_explicit_metrics() -> None:
    # Metrics are mandatory: the service no longer infers them from a task type.
    without_metrics = {k: v for k, v in REQUEST_BODY.items() if k != "metrics"}
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate(without_metrics)
    # An empty metrics list is rejected too.
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate({**REQUEST_BODY, "metrics": []})


def test_reference_only_request_is_valid() -> None:
    # The interaction may be supplied by reference (an inference_id to resolve).
    request = EvaluateRequest.model_validate(
        {"inference_id": "inf-9", "metrics": ["faithfulness"]}
    )
    assert request.inference_id == "inf-9"
    assert request.input_text is None


def test_reference_and_inline_together_are_rejected() -> None:
    # Reference and inline are mutually exclusive.
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate({**REQUEST_BODY, "inference_id": "inf-9"})


def test_partial_inline_without_reference_is_rejected() -> None:
    # A half-specified inline interaction (missing output_text) is rejected.
    body = {k: v for k, v in REQUEST_BODY.items() if k != "output_text"}
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate(body)


async def test_response_body_matches_the_contract() -> None:
    response = await _coordinator().evaluate(
        EvaluateRequest.model_validate(REQUEST_BODY)
    )
    payload = response.model_dump()

    assert set(payload) == {"results", "contract_version"}
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["results"], "expected at least one scored metric"
    for result in payload["results"]:
        assert set(result) == {
            "metric_name",
            "score",
            "reasoning",
            "evaluator_name",
            "evaluator_version",
        }
        assert isinstance(result["score"], float)
    assert {r["metric_name"] for r in payload["results"]} == {
        "faithfulness",
        "answer_relevance",
    }


def test_response_model_accepts_the_documented_shape() -> None:
    example = EvaluateResponse.model_validate(
        {
            "results": [
                {
                    "metric_name": "faithfulness",
                    "score": 0.91,
                    "reasoning": "The summary is grounded in the source text.",
                    "evaluator_name": "faithfulness",
                    "evaluator_version": "v1",
                }
            ]
        }
    )
    assert example.results[0].metric_name == "faithfulness"
    assert example.results[0].score == 0.91
