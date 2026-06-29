"""Custom judge: the caller supplies the rubric as a prompt.

The generic extension point — score against any user-defined criterion without a
new judge class. The rubric comes from ``config["prompt"]``; the case's
input/context/output/reference are all rendered so the rubric can reference them.
"""

from __future__ import annotations

from collections.abc import Mapping

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.judges.base import LLMJudge
from arc_eval_service.judges.builtins._render import context_block, section
from arc_eval_service.schemas.models import ConfigValue, EvaluationCase


class CustomJudge(LLMJudge):
    """Score against a caller-supplied rubric (``config['prompt']``)."""

    name: str = "custom"
    description: str = "Score against a caller-supplied rubric/prompt."
    requires: tuple[str, ...] = ("output",)

    def _instructions(self, config: Mapping[str, ConfigValue]) -> str:
        rubric = config.get("prompt")
        if not isinstance(rubric, str) or not rubric.strip():
            raise EvaluationError("custom judge requires a non-empty 'prompt' (rubric)")
        return (
            "You are an evaluation judge. Apply the following rubric and score "
            f"the case accordingly.\n\nRUBRIC:\n{rubric.strip()}"
        )

    def _render(self, case: EvaluationCase) -> str:
        return (
            section("Question", case.input)
            + context_block(case)
            + section("Answer", case.output)
            + section("Reference", case.reference)
        )
