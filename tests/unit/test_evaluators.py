"""Unit tests for evaluator strategy implementations and the registry."""

import pytest

from arc_eval_service.core.errors import EvaluationError, UnknownEvaluatorError
from arc_eval_service.evaluators.cost import CostEvaluator
from arc_eval_service.evaluators.exact_match import ExactMatchEvaluator
from arc_eval_service.evaluators.heuristic import HeuristicEvaluator
from arc_eval_service.evaluators.latency import LatencyEvaluator
from arc_eval_service.evaluators.regex import RegexEvaluator
from arc_eval_service.evaluators.registry import EvaluatorRegistry, default_registry
from arc_eval_service.evaluators.token import TokenEvaluator
from arc_eval_service.schemas.models import (
    ConfigValue,
    EvaluationCase,
    EvaluatorInput,
)

pytestmark = pytest.mark.unit


def _input(case: EvaluationCase, **config: ConfigValue) -> EvaluatorInput:
    return EvaluatorInput(case=case, config=dict(config))


# -- exact match ----------------------------------------------------------


def test_exact_match_passes_on_identical_text():
    case = EvaluationCase(request_id="r1", output="hello", reference="hello")
    result = ExactMatchEvaluator().evaluate(_input(case))
    assert result.passed is True
    assert result.score == 1.0


def test_exact_match_case_insensitive():
    case = EvaluationCase(request_id="r1", output="Hello", reference="hello")
    result = ExactMatchEvaluator().evaluate(_input(case, case_sensitive=False))
    assert result.passed is True


def test_exact_match_fails_when_different():
    case = EvaluationCase(request_id="r1", output="hi", reference="hello")
    result = ExactMatchEvaluator().evaluate(_input(case))
    assert result.passed is False
    assert result.score == 0.0


def test_exact_match_requires_reference():
    case = EvaluationCase(request_id="r1", output="hello")
    with pytest.raises(EvaluationError):
        ExactMatchEvaluator().evaluate(_input(case))


# -- regex ----------------------------------------------------------------


def test_regex_search_matches():
    case = EvaluationCase(request_id="r1", output="order id: 12345")
    result = RegexEvaluator().evaluate(_input(case, pattern=r"\d{5}"))
    assert result.passed is True


def test_regex_fullmatch_mode():
    case = EvaluationCase(request_id="r1", output="12345")
    result = RegexEvaluator().evaluate(_input(case, pattern=r"\d{5}", mode="fullmatch"))
    assert result.passed is True


def test_regex_invalid_pattern_raises():
    case = EvaluationCase(request_id="r1", output="x")
    with pytest.raises(EvaluationError):
        RegexEvaluator().evaluate(_input(case, pattern="("))


def test_regex_requires_pattern():
    case = EvaluationCase(request_id="r1", output="x")
    with pytest.raises(EvaluationError):
        RegexEvaluator().evaluate(_input(case))


# -- heuristic ------------------------------------------------------------


def test_heuristic_all_checks_pass():
    case = EvaluationCase(request_id="r1", output="A grounded, helpful answer.")
    result = HeuristicEvaluator().evaluate(
        _input(case, min_length=5, forbid_refusal=True)
    )
    assert result.passed is True
    assert result.score == 1.0


def test_heuristic_partial_score():
    case = EvaluationCase(request_id="r1", output="I cannot help with that.")
    result = HeuristicEvaluator().evaluate(
        _input(case, min_length=1, forbid_refusal=True)
    )
    # min_length passes, no_refusal fails -> 1/2.
    assert result.score == 0.5
    assert result.passed is False


# -- latency --------------------------------------------------------------


def test_latency_within_budget_passes():
    case = EvaluationCase(request_id="r1", latency_ms=100.0)
    result = LatencyEvaluator().evaluate(_input(case, threshold_ms=200))
    assert result.passed is True
    assert result.score == 1.0


def test_latency_over_budget_degrades():
    case = EvaluationCase(request_id="r1", latency_ms=400.0)
    result = LatencyEvaluator().evaluate(_input(case, threshold_ms=200))
    assert result.passed is False
    assert result.score == 0.5


def test_latency_requires_metric():
    case = EvaluationCase(request_id="r1")
    with pytest.raises(EvaluationError):
        LatencyEvaluator().evaluate(_input(case, threshold_ms=200))


# -- token ----------------------------------------------------------------


def test_token_within_budget_passes():
    case = EvaluationCase(request_id="r1", prompt_tokens=10, completion_tokens=20)
    result = TokenEvaluator().evaluate(_input(case, max_total_tokens=100))
    assert result.passed is True


def test_token_requires_a_count():
    case = EvaluationCase(request_id="r1")
    with pytest.raises(EvaluationError):
        TokenEvaluator().evaluate(_input(case, max_total_tokens=100))


# -- cost -----------------------------------------------------------------


def test_cost_within_budget_passes():
    case = EvaluationCase(request_id="r1", cost_usd=0.01)
    result = CostEvaluator().evaluate(_input(case, max_cost_usd=0.05))
    assert result.passed is True


def test_cost_over_budget_fails():
    case = EvaluationCase(request_id="r1", cost_usd=0.10)
    result = CostEvaluator().evaluate(_input(case, max_cost_usd=0.05))
    assert result.passed is False


def test_cost_bad_config_type_raises():
    case = EvaluationCase(request_id="r1", cost_usd=0.10)
    with pytest.raises(EvaluationError):
        CostEvaluator().evaluate(_input(case, max_cost_usd="cheap"))


# -- registry -------------------------------------------------------------


def test_default_registry_has_all_mvp_evaluators():
    registry = default_registry()
    names = {e.name for e in registry.available()}
    assert names == {"exact_match", "regex", "heuristic", "latency", "token", "cost"}


def test_registry_get_unknown_raises():
    registry = default_registry()
    with pytest.raises(UnknownEvaluatorError):
        registry.get("does-not-exist")


def test_registry_rejects_duplicate_registration():
    registry = EvaluatorRegistry()
    registry.register(CostEvaluator())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(CostEvaluator())
