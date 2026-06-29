"""Unit tests for judges: pure prompt building + verdict parsing."""

import pytest

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.judges.base import parse_verdict
from arc_eval_service.judges.builtins import (
    AnswerRelevanceJudge,
    CustomJudge,
    FaithfulnessJudge,
    SafetyJudge,
)
from arc_eval_service.judges.registry import default_registry
from arc_eval_service.schemas.models import EvaluationCase

pytestmark = pytest.mark.unit


def test_registry_has_only_llm_judges() -> None:
    names = {j.name for j in default_registry().available()}
    assert names == {"faithfulness", "answer_relevance", "safety", "custom"}


def test_faithfulness_prompt_includes_context_and_answer() -> None:
    case = EvaluationCase(
        request_id="r", output="Paris", context=["France capital Paris"]
    )
    prompt = FaithfulnessJudge().build_prompt(case, {})
    assert "Context" in prompt.user
    assert "Paris" in prompt.user
    assert "JSON" in (prompt.system or "")


def test_answer_relevance_prompt_includes_question() -> None:
    case = EvaluationCase(request_id="r", input="capital of France?", output="Paris")
    prompt = AnswerRelevanceJudge().build_prompt(case, {})
    assert "capital of France?" in prompt.user
    assert "Paris" in prompt.user


def test_custom_judge_requires_a_rubric() -> None:
    case = EvaluationCase(request_id="r", output="x")
    with pytest.raises(EvaluationError):
        CustomJudge().build_prompt(case, {})


def test_custom_judge_embeds_rubric() -> None:
    case = EvaluationCase(request_id="r", output="x")
    prompt = CustomJudge().build_prompt(case, {"prompt": "grade politeness"})
    assert "grade politeness" in (prompt.system or "")


def test_safety_threshold_is_strict() -> None:
    assert SafetyJudge().default_threshold == 0.8


@pytest.mark.parametrize(
    "text",
    [
        '{"score": 0.7, "label": "ok", "explanation": "fine"}',
        'prefix ```json\n{"score": 0.7, "label": "ok"}\n``` suffix',
        'The verdict is {"score": 0.7} based on the rubric.',
    ],
)
def test_parse_verdict_tolerates_loose_json(text: str) -> None:
    verdict = parse_verdict(text)
    assert verdict.score == 0.7


def test_parse_verdict_clamps_out_of_range() -> None:
    assert parse_verdict('{"score": 5}').score == 1.0
    assert parse_verdict('{"score": -2}').score == 0.0


def test_parse_verdict_rejects_non_numeric_score() -> None:
    with pytest.raises(EvaluationError):
        parse_verdict('{"score": "high"}')


def test_parse_verdict_rejects_missing_json() -> None:
    with pytest.raises(EvaluationError):
        parse_verdict("no json here")
