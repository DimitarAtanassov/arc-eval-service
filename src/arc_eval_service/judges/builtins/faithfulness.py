"""Faithfulness / groundedness judge: is the answer supported by the context?"""

from __future__ import annotations

from collections.abc import Mapping

from arc_eval_service.judges.base import LLMJudge
from arc_eval_service.judges.builtins._render import context_block, section
from arc_eval_service.schemas.models import ConfigValue, EvaluationCase


class FaithfulnessJudge(LLMJudge):
    """Score how well the output is grounded in the provided context."""

    name: str = "faithfulness"
    description: str = (
        "Is the answer supported by the provided context (no hallucination)?"
    )
    requires: tuple[str, ...] = ("output", "context")

    def _instructions(self, config: Mapping[str, ConfigValue]) -> str:
        return (
            "You are a strict faithfulness judge. Score how well the ANSWER is "
            "supported by the CONTEXT. 1 means every claim is grounded in the "
            "context; 0 means the answer is unsupported or contradicts it. "
            "Penalise any claim not entailed by the context."
        )

    def _render(self, case: EvaluationCase) -> str:
        return context_block(case) + section("Answer", case.output)
