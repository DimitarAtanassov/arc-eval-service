"""Service-level tests: a buggy evaluator must not strand or 500 the request."""

from typing import ClassVar

import pytest

from arc_eval_service.evaluators.base import Evaluator
from arc_eval_service.evaluators.exact_match import ExactMatchEvaluator
from arc_eval_service.evaluators.registry import EvaluatorRegistry
from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    EvaluatorInput,
    EvaluatorSpec,
)
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.storage.memory import InMemoryEvaluationStore

pytestmark = pytest.mark.unit


class BoomEvaluator(Evaluator):
    name: ClassVar[str] = "boom"
    description: ClassVar[str] = "Always raises an unexpected error."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        raise RuntimeError("kaboom")


def _service() -> EvaluationService:
    registry = EvaluatorRegistry()
    registry.register(ExactMatchEvaluator())
    registry.register(BoomEvaluator())
    return EvaluationService(store=InMemoryEvaluationStore(), registry=registry)


async def test_unexpected_evaluator_error_is_contained():
    service = _service()
    request = EvaluationRequest(
        case=EvaluationCase(request_id="r1", output="x"),
        evaluators=[EvaluatorSpec(name="boom")],
    )
    record = await service.evaluate(request)
    assert record.status is EvaluationStatus.FAILED
    assert record.results[0].error is not None
    assert record.aggregate_score is None


async def test_one_buggy_evaluator_does_not_sink_the_rest():
    service = _service()
    request = EvaluationRequest(
        case=EvaluationCase(request_id="r1", output="hi", reference="hi"),
        evaluators=[EvaluatorSpec(name="exact_match"), EvaluatorSpec(name="boom")],
    )
    record = await service.evaluate(request)
    results = {r.evaluator_name: r for r in record.results}
    assert results["exact_match"].passed is True
    assert results["boom"].error is not None
