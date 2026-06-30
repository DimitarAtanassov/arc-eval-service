"""Unit tests for the judge engine: a failing metric/model degrades, never raises."""

import pytest

from arc_eval_service.core.errors import ModelError, UnknownModelError
from arc_eval_service.evaluation.schemas import EvaluationCase, MetricSpec
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.judging.model import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry
from arc_eval_service.metrics.registry import default_registry

pytestmark = pytest.mark.unit

GOOD = '{"score": 0.9, "label": "pass", "explanation": "ok"}'


class _StubModel(JudgeModel):
    provider = "stub"

    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.name = "stub-model"
        self._text = text
        self._fail = fail

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        if self._fail:
            raise ModelError("stub failure")
        return ModelCompletion(text=self._text, model=self.name)


class _StubRegistry(ModelRegistry):
    def __init__(self, *, text: str = GOOD, fail: bool = False) -> None:
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


def _engine(*, text: str = GOOD, fail: bool = False) -> JudgeEngine:
    return JudgeEngine(
        metrics=default_registry(), models=_StubRegistry(text=text, fail=fail)
    )


async def test_scores_a_passing_metric() -> None:
    result = await _engine().score(
        MetricSpec(metric="safety"),
        EvaluationCase(request_id="r", output="hi"),
        case_id="c1",
    )
    assert result.metric == "safety" and result.error is None
    assert result.score == 0.9 and result.passed is True
    assert result.model == "stub-model"


async def test_model_failure_is_contained() -> None:
    result = await _engine(fail=True).score(
        MetricSpec(metric="safety"),
        EvaluationCase(request_id="r", output="x"),
        case_id="c1",
    )
    assert result.error is not None and result.score == 0.0 and result.passed is False


async def test_missing_required_field_degrades() -> None:
    # faithfulness requires context; absent -> errored result, not an exception.
    result = await _engine().score(
        MetricSpec(metric="faithfulness"),
        EvaluationCase(request_id="r", output="x"),
        case_id="c1",
    )
    assert result.error is not None


async def test_unparseable_verdict_degrades() -> None:
    result = await _engine(text="no json here").score(
        MetricSpec(metric="safety"),
        EvaluationCase(request_id="r", output="x"),
        case_id="c1",
    )
    assert result.error is not None


async def test_pass_threshold_override_from_config() -> None:
    result = await _engine().score(
        MetricSpec(metric="safety", config={"pass_threshold": 0.95}),
        EvaluationCase(request_id="r", output="hi"),
        case_id="c1",
    )
    assert result.score == 0.9 and result.passed is False
