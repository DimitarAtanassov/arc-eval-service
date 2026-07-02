"""Unit tests for the prompt library: loading, validation, and rendering."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arc_eval_service.core.errors import UnknownJudgeError, UnknownMetricError
from arc_eval_service.evaluation.schemas import EvaluationCase
from arc_eval_service.prompts.loader import load_library
from arc_eval_service.prompts.render import render_case
from arc_eval_service.prompts.schema import MetricDefinition

pytestmark = pytest.mark.unit


def test_bundled_library_loads_expected_metrics_and_judges() -> None:
    library = load_library()
    assert set(library.metrics) == {"faithfulness", "answer_relevance", "safety"}
    assert set(library.judges) == {"default", "careful"}


def test_default_judge_has_no_system_prompt_but_careful_does() -> None:
    library = load_library()
    assert library.judge("default").system_prompt is None
    assert library.judge("careful").system_prompt is not None


def test_bundled_metrics_declare_requires_and_thresholds() -> None:
    library = load_library()
    assert library.metric("faithfulness").requires == ("output", "context")
    assert library.metric("safety").threshold == 0.8


def test_unknown_metric_and_judge_raise() -> None:
    library = load_library()
    with pytest.raises(UnknownMetricError):
        library.metric("nope")
    with pytest.raises(UnknownJudgeError):
        library.judge("nope")


def test_metric_definition_requires_a_rubric() -> None:
    with pytest.raises(ValidationError):
        MetricDefinition.model_validate({"template": "{output}"})


def test_load_library_from_path(tmp_path) -> None:
    (tmp_path / "metrics").mkdir()
    (tmp_path / "judges").mkdir()
    (tmp_path / "metrics" / "echo.yaml").write_text(
        "rubric: Grade it.\ntemplate: '{output}'\nrequires: [output]\n",
        encoding="utf-8",
    )
    (tmp_path / "judges" / "default.yaml").write_text(
        "temperature: 0.0\n", encoding="utf-8"
    )

    library = load_library(str(tmp_path))
    assert library.metric("echo").rubric == "Grade it."
    assert library.judge("default").temperature == 0.0


def test_render_case_fills_slots_and_numbers_context() -> None:
    template = "### Context\n{context}\n### Answer\n{output}"
    case = EvaluationCase(request_id="r", output="Paris.", context=["a", "b"])
    rendered = render_case(template, case)
    assert "[1] a" in rendered and "[2] b" in rendered
    assert "### Answer\nParis." in rendered


def test_render_case_leaves_absent_fields_empty() -> None:
    case = EvaluationCase(request_id="r", output="hi")
    rendered = render_case("Q: {input}\nA: {output}", case)
    assert rendered == "Q: \nA: hi"
