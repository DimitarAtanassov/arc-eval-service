"""Unit tests for the pure wire<->domain<->record mappers (no model, no database)."""

from __future__ import annotations

import pytest

from arc_eval_service.catalog import Catalog
from arc_eval_service.catalog.judge import JudgeDefinition
from arc_eval_service.catalog.metric import MetricDefinition
from arc_eval_service.domain.evaluation import MetricScore
from arc_eval_service.services.interaction import Interaction
from arc_eval_service.services.mapping import (
    build_case,
    metric_version,
    new_eval_request,
    new_eval_results,
    to_metric_result,
)

pytestmark = pytest.mark.unit


def _library() -> Catalog:
    return Catalog(
        metrics={
            "safety": MetricDefinition(
                rubric="Rate safety.",
                template="{output}",
                requires=("output",),
                threshold=0.5,
                version="v3",
            )
        },
        judges={"default": JudgeDefinition(model_profile="default")},
    )


def _interaction() -> Interaction:
    return Interaction(input_text="source", output_text="summary", metrics=("safety",))


def test_build_case_passes_input_as_grounding_context() -> None:
    case = build_case(_interaction(), request_id="req-1")
    assert case.request_id == "req-1"
    assert case.input == "source"
    assert case.output == "summary"
    # input_text doubles as grounding context for grounded metrics.
    assert case.context == ["source"]


def test_metric_version_returns_none_for_unknown_metric() -> None:
    assert metric_version(_library(), "safety") == "v3"
    assert metric_version(_library(), "does-not-exist") is None


def test_to_metric_result_carries_evaluator_version() -> None:
    score = MetricScore(metric="safety", score=0.9, passed=True, explanation="ok")
    result = to_metric_result(score, library=_library())
    assert result.metric_name == "safety"
    assert result.evaluator_name == "safety"
    assert result.evaluator_version == "v3"
    assert result.reasoning == "ok"


def test_new_eval_request_carries_only_the_scored_text() -> None:
    row = new_eval_request(_interaction(), request_id="req-1")
    assert row.id == "req-1"
    assert row.input_text == "source"
    assert row.output_text == "summary"
    # The evaluator scores supplied text and carries no lab correlation.
    assert row.prompt is None
    assert row.inference_id is None
    assert row.model_id is None
    assert row.request_metadata == {}


def test_new_eval_results_omit_judge_json_for_errored_score() -> None:
    case = build_case(_interaction(), request_id="req-1")
    scored = [
        MetricScore(
            metric="safety",
            model="stub-judge",
            score=0.9,
            passed=True,
            judge_name="default",
            system_prompt="Rate safety.",
        ),
        # Errored score: no model resolved, so no judge provenance is recorded.
        MetricScore(metric="safety", score=0.0, passed=False, error="boom"),
    ]
    rows = new_eval_results(scored, request_id="req-1", case=case, library=_library())
    assert rows[0].judge is not None and rows[0].judge["model"] == "stub-judge"
    assert rows[1].judge is None and rows[1].error == "boom"
    # The evaluator writes no model correlation onto the result rows.
    assert all(row.inference_id is None and row.model_id is None for row in rows)
