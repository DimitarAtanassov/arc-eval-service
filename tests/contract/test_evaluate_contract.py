"""Contract tests: the ``POST /v1/evaluate`` request and response wire shapes.

These lock the evaluate contract: the caller sends the input, the output, and the
metrics, and receives one score per metric. If a field is renamed, added, or
removed, they fail, independent of any database or judge model.
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
from arc_eval_service.services.evaluation_service import EvaluationService
from arc_eval_service.services.interaction import Interaction

pytestmark = pytest.mark.contract

# The exact request body a caller sends to score a completed interaction.
REQUEST_BODY = {
    "input_text": "the source article",
    "output_text": "the summary",
    "metrics": ["faithfulness", "answer_relevance"],
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


def test_request_body_matches_the_contract() -> None:
    request = EvaluateRequest.model_validate(REQUEST_BODY)

    assert request.input_text == "the source article"
    assert request.output_text == "the summary"
    assert request.metrics == ["faithfulness", "answer_relevance"]


@pytest.mark.parametrize(
    "extra",
    [{"prompt": "x"}, {"inference_id": "inf-1"}, {"metadata": {}}],
)
def test_request_rejects_the_removed_fields(extra: dict[str, object]) -> None:
    # extra="forbid" turns the dropped fields into a 422 rather than a silent ignore.
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate({**REQUEST_BODY, **extra})


def test_request_requires_at_least_one_metric() -> None:
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate(
            {"input_text": "a", "output_text": "b", "metrics": []}
        )


async def test_response_matches_the_contract() -> None:
    interaction = Interaction(
        input_text="src", output_text="out", metrics=("faithfulness",)
    )

    response = (await _service().score(interaction)).response

    assert isinstance(response, EvaluateResponse)
    assert response.contract_version == CONTRACT_VERSION
    result = response.results[0]
    assert result.metric_name == "faithfulness"
    assert result.score == 0.91
    assert result.evaluator_name == "faithfulness"
    assert result.reasoning == "grounded in the source"
