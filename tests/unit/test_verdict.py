"""Unit tests for the strict-JSON verdict parser."""

import pytest

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.judging.verdict import parse_verdict

pytestmark = pytest.mark.unit


def test_parses_clean_json() -> None:
    verdict = parse_verdict('{"score": 0.7, "label": "ok", "explanation": "fine"}')
    assert verdict.score == 0.7
    assert verdict.label == "ok"
    assert verdict.explanation == "fine"


def test_parses_chatty_or_fenced_json() -> None:
    assert parse_verdict('Sure!\n```json\n{"score": 1}\n```').score == 1.0


def test_clamps_score_to_unit_interval() -> None:
    assert parse_verdict('{"score": 2.5}').score == 1.0
    assert parse_verdict('{"score": -1}').score == 0.0


def test_no_json_raises() -> None:
    with pytest.raises(EvaluationError):
        parse_verdict("no json here")


def test_missing_score_raises() -> None:
    with pytest.raises(EvaluationError):
        parse_verdict('{"label": "x"}')


def test_non_numeric_score_raises() -> None:
    with pytest.raises(EvaluationError):
        parse_verdict('{"score": "high"}')
