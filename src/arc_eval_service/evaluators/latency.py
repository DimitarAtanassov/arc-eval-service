"""Latency evaluator: response latency must stay within a budget."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.base import Evaluator, ratio_score, require_number
from arc_eval_service.schemas.models import EvaluationResult, EvaluatorInput


class LatencyEvaluator(Evaluator):
    """Pass when ``latency_ms`` is within ``threshold_ms``.

    Config:
        ``threshold_ms`` (number, required): latency budget in milliseconds.
    """

    name: ClassVar[str] = "latency"
    description: ClassVar[str] = "Response latency must stay within a budget (ms)."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        case = data.case
        if case.latency_ms is None:
            raise EvaluationError("latency requires 'latency_ms'")

        threshold = require_number(data.config, "threshold_ms")
        latency = case.latency_ms
        passed = latency <= threshold
        return EvaluationResult(
            evaluator_name=self.name,
            score=round(ratio_score(threshold, latency), 4),
            passed=passed,
            details={
                "latency_ms": f"{latency:.2f}",
                "threshold_ms": f"{threshold:.2f}",
            },
        )
