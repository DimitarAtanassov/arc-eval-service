"""Contract tests: the ``POST /v1/evaluate`` request and response wire shapes.

These lock the contract that arc-model-lab depends on. If a field is renamed,
added, or removed, they fail -- independent of any database or judge model.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.catalog import load_catalog
from arc_eval_service.db.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.services.evaluation_service import EvaluationService

pytestmark = pytest.mark.contract

# The exact request body arc-model-lab sends after inference.
REQUEST_BODY = {
    "task_type": "summarization",
    "input_text": "the source article",
    "output_text": "the summary",
    "prompt": "Summarize the article.",
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

    async def create(self, item: NewEvalRequest) -> None:
        return None


class _NoopResultRepo(EvaluationResultRepository):
    def __init__(self) -> None:
        pass

    async def create_many(self, items: Sequence[NewEvaluationResult]) -> None:
        return None


def _service() -> EvaluationService:
    return EvaluationService(
        engine=_FakeEngine(),
        library=load_catalog(),
        requests=_NoopRequestRepo(),
        results=_NoopResultRepo(),
    )


def test_request_body_matches_the_contract() -> None:
    request = EvaluateRequest.model_validate(REQUEST_BODY)

    assert request.task_type == "summarization"
    assert request.input_text == "the source article"
    assert request.output_text == "the summary"
    assert request.prompt == "Summarize the article."
    assert request.metadata.inference_id == "inf-1"
    assert request.metadata.model_id == "mdl-1"


def test_request_accepts_optional_metrics() -> None:
    # Omitted: the caller relies on task-type policy (the default contract).
    assert EvaluateRequest.model_validate(REQUEST_BODY).metrics is None

    # Present: the caller selects the metrics to score explicitly.
    selective = EvaluateRequest.model_validate(
        {**REQUEST_BODY, "metrics": ["faithfulness"]}
    )
    assert selective.metrics == ["faithfulness"]


async def test_response_body_matches_the_contract() -> None:
    response = await _service().evaluate(EvaluateRequest.model_validate(REQUEST_BODY))
    payload = response.model_dump()

    assert set(payload) == {"results"}
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
