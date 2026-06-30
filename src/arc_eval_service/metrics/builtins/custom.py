"""Custom metric: the caller supplies the rubric as a prompt.

The generic extension point: score against any user-defined criterion without a
new metric class. The rubric comes from ``config["prompt"]``; the case's
input/context/output/reference are all rendered so the rubric can reference them.
"""

from __future__ import annotations

from collections.abc import Mapping

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluation.schemas import ConfigValue, EvaluationCase
from arc_eval_service.metrics.render import context_block, section


class CustomMetric:
    """Score against a caller-supplied rubric (``config['prompt']``)."""

    name = "custom"
    description = "Score against a caller-supplied rubric/prompt."
    requires: tuple[str, ...] = ("output",)
    threshold = 0.5

    def instructions(self, config: Mapping[str, ConfigValue]) -> str:
        rubric = config.get("prompt")
        if not isinstance(rubric, str) or not rubric.strip():
            raise EvaluationError(
                "custom metric requires a non-empty 'prompt' (rubric)"
            )
        return (
            "You are an evaluation judge. Apply the following rubric and score "
            f"the case accordingly.\n\nRUBRIC:\n{rubric.strip()}"
        )

    def render(self, case: EvaluationCase) -> str:
        return (
            section("Question", case.input)
            + context_block(case)
            + section("Answer", case.output)
            + section("Reference", case.reference)
        )
