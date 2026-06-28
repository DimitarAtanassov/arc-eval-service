"""Latency evaluator: response latency must stay within a budget."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.budget import BudgetEvaluator
from arc_eval_service.schemas.models import EvaluationCase


class LatencyEvaluator(BudgetEvaluator):
    """Pass when ``latency_ms`` is within ``threshold_ms``.

    Config:
        ``threshold_ms`` (number, required): latency budget in milliseconds.
    """

    name: ClassVar[str] = "latency"
    description: ClassVar[str] = "Response latency must stay within a budget (ms)."
    config_key: ClassVar[str] = "threshold_ms"
    value_label: ClassVar[str] = "latency_ms"
    limit_label: ClassVar[str] = "threshold_ms"
    value_format: ClassVar[str] = ".2f"

    def _measure(self, case: EvaluationCase) -> float:
        if case.latency_ms is None:
            raise EvaluationError("latency requires 'latency_ms'")
        return case.latency_ms
