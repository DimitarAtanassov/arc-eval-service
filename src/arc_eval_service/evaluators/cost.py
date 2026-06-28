"""Cost evaluator: interaction cost must stay within a budget."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.budget import BudgetEvaluator
from arc_eval_service.schemas.models import EvaluationCase


class CostEvaluator(BudgetEvaluator):
    """Pass when ``cost_usd`` is within ``max_cost_usd``.

    Config:
        ``max_cost_usd`` (number, required): cost budget in US dollars.
    """

    name: ClassVar[str] = "cost"
    description: ClassVar[str] = "Interaction cost must stay within a budget (USD)."
    config_key: ClassVar[str] = "max_cost_usd"
    value_label: ClassVar[str] = "cost_usd"
    limit_label: ClassVar[str] = "max_cost_usd"
    value_format: ClassVar[str] = ".6f"

    def _measure(self, case: EvaluationCase) -> float:
        if case.cost_usd is None:
            raise EvaluationError("cost requires 'cost_usd'")
        return case.cost_usd
