"""Answer-relevance metric: does the answer address the question?"""

from __future__ import annotations

from collections.abc import Mapping

from arc_eval_service.evaluation.schemas import ConfigValue, EvaluationCase
from arc_eval_service.metrics.render import section


class AnswerRelevanceMetric:
    """Score how directly the output answers the input question."""

    name = "answer_relevance"
    description = "Does the answer address the question asked?"
    requires: tuple[str, ...] = ("input", "output")
    threshold = 0.5

    def instructions(self, config: Mapping[str, ConfigValue]) -> str:
        return (
            "You are a relevance judge. Score how directly and completely the "
            "ANSWER addresses the QUESTION. 1 means a focused, complete answer; "
            "0 means off-topic or evasive. Ignore factual correctness here."
        )

    def render(self, case: EvaluationCase) -> str:
        return section("Question", case.input) + section("Answer", case.output)
