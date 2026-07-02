"""Unit tests for domain error classes."""

from __future__ import annotations

import pytest

from arc_eval_service.domain.errors import (
    EvaluationError,
    ModelError,
    UnknownJudgeError,
    UnknownMetricError,
    UnknownModelError,
)

pytestmark = pytest.mark.unit


def test_unknown_metric_error_supports_plural_and_single_names() -> None:
    single = UnknownMetricError("foo")
    plural = UnknownMetricError(["foo", "bar"])

    assert single.name == "foo"
    assert single.names == ("foo",)
    assert str(single) == "unknown metric 'foo'"
    assert plural.name == "foo"
    assert plural.names == ("foo", "bar")
    assert str(plural) == "unknown metrics: 'foo', 'bar'"


def test_unknown_judge_and_model_errors_capture_names() -> None:
    judge_error = UnknownJudgeError("careful")
    model_error = UnknownModelError("default")

    assert judge_error.name == "careful"
    assert str(judge_error) == "unknown judge 'careful'"
    assert model_error.name == "default"
    assert str(model_error) == "unknown model profile 'default'"


def test_basic_evaluation_and_model_errors_are_instantiable() -> None:
    assert isinstance(EvaluationError(), EvaluationError)
    assert isinstance(ModelError(), ModelError)
