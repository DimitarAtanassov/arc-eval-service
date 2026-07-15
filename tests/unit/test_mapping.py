"""Unit tests for the pure wire<->domain<->record mappers (no model, no database)."""

from __future__ import annotations

import pytest

from arc_eval_service.api.schemas import EvaluationMetadata
from arc_eval_service.catalog import Catalog
from arc_eval_service.catalog.judge import JudgeDefinition
from arc_eval_service.catalog.metric import MetricDefinition
from arc_eval_service.domain.evaluation import MetricScore
from arc_eval_service.services.interaction import ResolvedInteraction
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


def _interaction() -> ResolvedInteraction:
    return ResolvedInteraction(
        input_text="source",
        output_text="summary",
        prompt="Summarize:",
        metrics=("safety",),
        metadata=EvaluationMetadata(inference_id="inf-1", model_id="mdl-1"),
    )


def test_build_case_passes_input_as_grounding_context() -> None:
    case = build_case(_interaction(), request_id="req-1")
    assert case.request_id == "req-1"
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


def test_new_eval_request_flattens_metadata() -> None:
    row = new_eval_request(_interaction(), request_id="req-1")
    assert row.id == "req-1"
    assert row.inference_id == "inf-1"
    assert row.model_id == "mdl-1"
    assert row.request_metadata["inference_id"] == "inf-1"


def test_new_eval_results_omits_judge_json_for_errored_score() -> None:
    interaction = _interaction()
    case = build_case(interaction, request_id="req-1")
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
    rows = new_eval_results(
        scored,
        request_id="req-1",
        interaction=interaction,
        case=case,
        library=_library(),
    )
    assert rows[0].judge is not None and rows[0].judge["model"] == "stub-judge"
    assert rows[1].judge is None and rows[1].error == "boom"
    assert all(row.prompt is not None for row in rows)
