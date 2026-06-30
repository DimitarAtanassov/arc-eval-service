"""Unit tests for metrics: pure rubric + case rendering."""

import pytest

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluation.schemas import EvaluationCase
from arc_eval_service.metrics.builtins.answer_relevance import AnswerRelevanceMetric
from arc_eval_service.metrics.builtins.custom import CustomMetric
from arc_eval_service.metrics.builtins.faithfulness import FaithfulnessMetric
from arc_eval_service.metrics.builtins.safety import SafetyMetric
from arc_eval_service.metrics.registry import default_registry

pytestmark = pytest.mark.unit


def test_default_registry_has_builtin_metrics() -> None:
    names = {m.name for m in default_registry().available()}
    assert names == {"faithfulness", "answer_relevance", "safety", "custom"}


def test_safety_renders_output_only() -> None:
    out = SafetyMetric().render(EvaluationCase(request_id="r", output="hello"))
    assert "Output" in out and "hello" in out


def test_faithfulness_renders_context_and_answer() -> None:
    metric = FaithfulnessMetric()
    out = metric.render(
        EvaluationCase(request_id="r", output="a", context=["c1", "c2"])
    )
    assert "Context" in out and "[1] c1" in out and "Answer" in out
    assert metric.requires == ("output", "context")


def test_answer_relevance_renders_question_and_answer() -> None:
    out = AnswerRelevanceMetric().render(
        EvaluationCase(request_id="r", input="q", output="a")
    )
    assert "Question" in out and "Answer" in out


def test_custom_uses_caller_rubric() -> None:
    system = CustomMetric().instructions({"prompt": "grade tone"})
    assert "grade tone" in system


def test_custom_requires_prompt() -> None:
    with pytest.raises(EvaluationError):
        CustomMetric().instructions({})


def test_thresholds() -> None:
    assert SafetyMetric().threshold == 0.8
    assert FaithfulnessMetric().threshold == 0.5
