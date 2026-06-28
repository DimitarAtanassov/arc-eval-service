"""Token-usage evaluator: total token count must stay within a budget."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.budget import BudgetEvaluator
from arc_eval_service.schemas.models import EvaluationCase


class TokenEvaluator(BudgetEvaluator):
    """Pass when total tokens are within ``max_total_tokens``.

    Total tokens = ``prompt_tokens`` + ``completion_tokens`` (each defaults to 0,
    but at least one must be present).

    Config:
        ``max_total_tokens`` (number, required).
    """

    name: ClassVar[str] = "token"
    description: ClassVar[str] = "Total token usage must stay within a budget."
    config_key: ClassVar[str] = "max_total_tokens"
    value_label: ClassVar[str] = "total_tokens"
    limit_label: ClassVar[str] = "max_total_tokens"
    value_format: ClassVar[str] = ".0f"

    def _measure(self, case: EvaluationCase) -> float:
        if case.prompt_tokens is None and case.completion_tokens is None:
            raise EvaluationError(
                "token requires 'prompt_tokens' and/or 'completion_tokens'"
            )
        return float((case.prompt_tokens or 0) + (case.completion_tokens or 0))
