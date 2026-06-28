"""Token-usage evaluator: total token count must stay within a budget."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.base import Evaluator, ratio_score, require_number
from arc_eval_service.schemas.models import EvaluationResult, EvaluatorInput


class TokenEvaluator(Evaluator):
    """Pass when total tokens are within ``max_total_tokens``.

    Total tokens = ``prompt_tokens`` + ``completion_tokens`` (each defaults to 0,
    but at least one must be present).

    Config:
        ``max_total_tokens`` (number, required).
    """

    name: ClassVar[str] = "token"
    description: ClassVar[str] = "Total token usage must stay within a budget."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        case = data.case
        if case.prompt_tokens is None and case.completion_tokens is None:
            raise EvaluationError(
                "token requires 'prompt_tokens' and/or 'completion_tokens'"
            )

        threshold = require_number(data.config, "max_total_tokens")
        total = (case.prompt_tokens or 0) + (case.completion_tokens or 0)
        passed = total <= threshold
        return EvaluationResult(
            evaluator_name=self.name,
            score=round(ratio_score(threshold, total), 4),
            passed=passed,
            details={
                "total_tokens": str(total),
                "max_total_tokens": f"{threshold:.0f}",
            },
        )
