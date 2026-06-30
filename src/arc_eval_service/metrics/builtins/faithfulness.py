"""Faithfulness metric: is the answer supported by the context?"""

from __future__ import annotations

from collections.abc import Mapping

from arc_eval_service.evaluation.schemas import ConfigValue, EvaluationCase
from arc_eval_service.metrics.render import context_block, section


class FaithfulnessMetric:
    """Score how well the output is grounded in the provided context."""

    name = "faithfulness"
    description = "Is the answer supported by the provided context (no hallucination)?"
    requires: tuple[str, ...] = ("output", "context")
    threshold = 0.5

    def instructions(self, config: Mapping[str, ConfigValue]) -> str:
        return (
            "You are a strict faithfulness judge. Score how well the ANSWER is "
            "supported by the CONTEXT. 1 means every claim is grounded in the "
            "context; 0 means the answer is unsupported or contradicts it. "
            "Penalise any claim not entailed by the context."
        )

    def render(self, case: EvaluationCase) -> str:
        return context_block(case) + section("Answer", case.output)
