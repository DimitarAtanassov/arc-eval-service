"""Service-level tests: a failing judge/model must not strand or 500 a request."""

import pytest

from arc_eval_service.core.errors import ModelError, UnknownModelError
from arc_eval_service.judges.registry import default_registry
from arc_eval_service.models.base import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.models.profiles import ModelProfile, ModelRegistry
from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRequest,
    EvaluationStatus,
    JudgeSpec,
)
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.storage.evaluation import InMemoryEvaluationStore

pytestmark = pytest.mark.unit

GOOD_VERDICT = '{"score": 0.9, "label": "pass", "explanation": "looks good"}'


class _StubModel(JudgeModel):
    provider = "stub"

    def __init__(self, text: str, *, fail: bool) -> None:
        self.name = "stub-model"
        self._text = text
        self._fail = fail

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        if self._fail:
            raise ModelError("stub failure")
        return ModelCompletion(text=self._text, model=self.name)


class _StubModelRegistry(ModelRegistry):
    def __init__(self, *, text: str, fail: bool) -> None:
        super().__init__(
            [ModelProfile(name="default", provider="openai_compatible", model="stub")],
            default="default",
        )
        self._text = text
        self._fail = fail

    def resolve(
        self, name: str | None = None, *, model_override: str | None = None
    ) -> JudgeModel:
        if not self.has(name):
            raise UnknownModelError(name or "default")
        return _StubModel(self._text, fail=self._fail)


def _service(*, text: str = GOOD_VERDICT, fail: bool = False) -> EvaluationService:
    return EvaluationService(
        store=InMemoryEvaluationStore(),
        judges=default_registry(),
        models=_StubModelRegistry(text=text, fail=fail),
    )


async def test_model_failure_is_contained() -> None:
    service = _service(fail=True)
    request = EvaluationRequest(
        case=EvaluationCase(request_id="r1", output="x"),
        judges=[JudgeSpec(judge="safety")],
    )
    record = await service.evaluate(request)
    assert record.status is EvaluationStatus.FAILED
    assert record.results[0].error is not None
    assert record.aggregate_score is None


async def test_missing_required_field_degrades_that_judge() -> None:
    service = _service()
    # faithfulness requires context; safety only needs output.
    request = EvaluationRequest(
        case=EvaluationCase(request_id="r1", output="hi"),
        judges=[JudgeSpec(judge="safety"), JudgeSpec(judge="faithfulness")],
    )
    record = await service.evaluate(request)
    results = {r.judge: r for r in record.results}
    assert results["safety"].error is None
    assert results["safety"].passed is True
    assert results["faithfulness"].error is not None  # missing context -> degraded


async def test_unparseable_verdict_degrades() -> None:
    service = _service(text="the model rambled with no json")
    request = EvaluationRequest(
        case=EvaluationCase(request_id="r1", output="x"),
        judges=[JudgeSpec(judge="safety")],
    )
    record = await service.evaluate(request)
    assert record.results[0].error is not None


async def test_record_stores_specs_and_rerun_links_parent() -> None:
    service = _service()
    request = EvaluationRequest(
        case=EvaluationCase(request_id="r1", output="hi"),
        judges=[JudgeSpec(judge="safety")],
    )
    record = await service.evaluate(request)
    assert [s.judge for s in record.specs] == ["safety"]

    rerun = await service.rerun(record.evaluation_id)
    assert rerun.rerun_of == record.evaluation_id
    assert rerun.evaluation_id != record.evaluation_id
    assert rerun.results[0].judge == "safety"
