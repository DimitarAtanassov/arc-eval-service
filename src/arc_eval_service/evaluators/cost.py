"""Cost evaluator: interaction cost must stay within a budget."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.base import Evaluator, ratio_score, require_number
from arc_eval_service.schemas.models import EvaluationResult, EvaluatorInput


class CostEvaluator(Evaluator):
    """Pass when ``cost_usd`` is within ``max_cost_usd``.

    Config:
        ``max_cost_usd`` (number, required): cost budget in US dollars.
    """

    name: ClassVar[str] = "cost"
    description: ClassVar[str] = "Interaction cost must stay within a budget (USD)."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        case = data.case
        if case.cost_usd is None:
            raise EvaluationError("cost requires 'cost_usd'")

        threshold = require_number(data.config, "max_cost_usd")
        cost = case.cost_usd
        passed = cost <= threshold
        return EvaluationResult(
            evaluator_name=self.name,
            score=round(ratio_score(threshold, cost), 4),
            passed=passed,
            details={
                "cost_usd": f"{cost:.6f}",
                "max_cost_usd": f"{threshold:.6f}",
            },
        )
