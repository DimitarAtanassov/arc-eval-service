"""Unit tests for the judge engine: judge/metric composition and degradation.

The model is stubbed (and captures the system prompt it receives), so these tests
verify how the engine composes the judge persona, the metric rubric and the
verdict instruction, and that any failure degrades to an errored result rather
than raising.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from arc_eval_service.catalog import Catalog
from arc_eval_service.catalog.judge import JudgeDefinition
from arc_eval_service.catalog.metric import MetricDefinition
from arc_eval_service.domain.errors import ModelError, UnknownModelError
from arc_eval_service.domain.evaluation import EvaluationCase
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.judging.ports import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry

pytestmark = pytest.mark.unit

GOOD = '{"score": 0.9, "label": "pass", "explanation": "ok"}'


def _library() -> Catalog:
    return Catalog(
        metrics={
            "safety": MetricDefinition(
                rubric="Rate safety.",
                template="### Output\n{output}",
                requires=("output",),
                threshold=0.5,
            ),
            "faithfulness": MetricDefinition(
                rubric="Rate faithfulness.",
                template="### Answer\n{output}",
                requires=("output", "context"),
                threshold=0.5,
            ),
        },
        judges={
            "default": JudgeDefinition(model_profile="default"),
            "careful": JudgeDefinition(
                version="v2",
                system_prompt="You are meticulous.",
                model_profile="default",
            ),
        },
    )


class _StubModel(JudgeModel):
    provider = "stub"

    def __init__(
        self, text: str, *, fail: bool = False, capture: list[str] | None = None
    ) -> None:
        self.name = "stub-model"
        self._text = text
        self._fail = fail
        self._capture = capture

    async def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        settings: ModelSettings,
        response_schema: type[BaseModel] | None = None,
    ) -> ModelCompletion:
        if self._capture is not None and system is not None:
            self._capture.append(system)
        if self._fail:
            raise ModelError("stub failure")
        return ModelCompletion(text=self._text, model=self.name)


class _StubRegistry(ModelRegistry):
    def __init__(
        self, *, text: str = GOOD, fail: bool = False, capture: list[str] | None = None
    ) -> None:
        super().__init__(
            [ModelProfile(name="default", provider="openai_compatible", model="stub")],
            default="default",
        )
        self._text = text
        self._fail = fail
        self._capture = capture

    def resolve(
        self, name: str | None = None, *, model_override: str | None = None
    ) -> JudgeModel:
        if not self.has(name):
            raise UnknownModelError(name or "default")
        return _StubModel(self._text, fail=self._fail, capture=self._capture)


def _engine(
    *, text: str = GOOD, fail: bool = False, capture: list[str] | None = None
) -> JudgeEngine:
    return JudgeEngine(
        library=_library(),
        models=_StubRegistry(text=text, fail=fail, capture=capture),
        default_judge="default",
    )


async def test_scores_a_passing_metric() -> None:
    result = await _engine().score(
        "safety", EvaluationCase(request_id="r", output="hi"), case_id="c1"
    )
    assert result.metric == "safety" and result.error is None
    assert result.score == 0.9 and result.passed is True
    assert result.model == "stub-model"
    assert result.judge_name == "default" and result.judge_version == "v1"
    assert result.prompt_template == "Rate safety."


async def test_default_judge_has_no_own_system_prompt() -> None:
    capture: list[str] = []
    await _engine(capture=capture).score(
        "safety", EvaluationCase(request_id="r", output="hi"), case_id="c1"
    )
    system = capture[0]
    # The rubric is the whole system prompt (no judge persona, no verdict text).
    assert system.startswith("Rate safety.")
    assert "You are meticulous." not in system


async def test_named_judge_prepends_its_system_prompt() -> None:
    capture: list[str] = []
    await _engine(capture=capture).score(
        "safety",
        EvaluationCase(request_id="r", output="hi"),
        case_id="c1",
        judge="careful",
    )
    system = capture[0]
    assert system.startswith("You are meticulous.")
    assert "Rate safety." in system


async def test_model_failure_is_contained() -> None:
    result = await _engine(fail=True).score(
        "safety", EvaluationCase(request_id="r", output="x"), case_id="c1"
    )
    assert result.error is not None and result.score == 0.0 and result.passed is False


async def test_missing_required_field_degrades() -> None:
    # faithfulness requires context; absent -> errored result, not an exception.
    result = await _engine().score(
        "faithfulness", EvaluationCase(request_id="r", output="x"), case_id="c1"
    )
    assert result.error is not None


async def test_unknown_metric_degrades() -> None:
    result = await _engine().score(
        "nope", EvaluationCase(request_id="r", output="x"), case_id="c1"
    )
    assert result.error is not None


async def test_unknown_judge_degrades() -> None:
    result = await _engine().score(
        "safety",
        EvaluationCase(request_id="r", output="x"),
        case_id="c1",
        judge="ghost",
    )
    assert result.error is not None


async def test_unparseable_verdict_degrades() -> None:
    result = await _engine(text="no json here").score(
        "safety", EvaluationCase(request_id="r", output="x"), case_id="c1"
    )
    assert result.error is not None
