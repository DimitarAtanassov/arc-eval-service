"""Answer-relevance judge: does the answer address the question?"""

from __future__ import annotations

from collections.abc import Mapping

from arc_eval_service.judges.base import LLMJudge
from arc_eval_service.judges.builtins._render import section
from arc_eval_service.schemas.models import ConfigValue, EvaluationCase


class AnswerRelevanceJudge(LLMJudge):
    """Score how directly the output answers the input question."""

    name: str = "answer_relevance"
    description: str = "Does the answer address the question asked?"
    requires: tuple[str, ...] = ("input", "output")

    def _instructions(self, config: Mapping[str, ConfigValue]) -> str:
        return (
            "You are a relevance judge. Score how directly and completely the "
            "ANSWER addresses the QUESTION. 1 means a focused, complete answer; "
            "0 means off-topic or evasive. Ignore factual correctness here."
        )

    def _render(self, case: EvaluationCase) -> str:
        return section("Question", case.input) + section("Answer", case.output)
