"""Unit tests for the evaluator catalog: loading, validation, and rendering."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arc_eval_service.catalog import load_catalog
from arc_eval_service.catalog.metric import MetricDefinition, render_case
from arc_eval_service.domain.errors import UnknownJudgeError, UnknownMetricError
from arc_eval_service.domain.evaluation import EvaluationCase

pytestmark = pytest.mark.unit


def test_bundled_catalog_loads_expected_metrics_and_judges() -> None:
    catalog = load_catalog()
    assert set(catalog.metrics) == {"faithfulness", "answer_relevance", "safety"}
    assert set(catalog.judges) == {"default", "careful"}


def test_default_judge_has_no_system_prompt_but_careful_does() -> None:
    catalog = load_catalog()
    assert catalog.judge("default").system_prompt is None
    assert catalog.judge("careful").system_prompt is not None


def test_bundled_metrics_declare_requires_and_thresholds() -> None:
    catalog = load_catalog()
    assert catalog.metric("faithfulness").requires == ("output", "context")
    assert catalog.metric("safety").threshold == 0.8


def test_unknown_metric_and_judge_raise() -> None:
    catalog = load_catalog()
    with pytest.raises(UnknownMetricError):
        catalog.metric("nope")
    with pytest.raises(UnknownJudgeError):
        catalog.judge("nope")


def test_metric_definition_requires_a_rubric() -> None:
    with pytest.raises(ValidationError):
        MetricDefinition.model_validate({"template": "{output}"})


def test_load_catalog_from_path(tmp_path) -> None:
    (tmp_path / "metric").mkdir()
    (tmp_path / "judge").mkdir()
    (tmp_path / "metric" / "echo.yaml").write_text(
        "rubric: Grade it.\ntemplate: '{output}'\nrequires: [output]\n",
        encoding="utf-8",
    )
    (tmp_path / "judge" / "default.yaml").write_text(
        "temperature: 0.0\n", encoding="utf-8"
    )

    catalog = load_catalog(str(tmp_path))
    assert catalog.metric("echo").rubric == "Grade it."
    assert catalog.judge("default").temperature == 0.0


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
