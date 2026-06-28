"""Shared base for budget-style evaluators (latency, token, cost).

These evaluators all share one shape: pull a single numeric metric off the case,
compare it against a configured upper bound and grade how far any overshoot
goes. Only the metric, the config key and the detail labels differ, so the
comparison and scoring live here once (Template Method); subclasses supply just
:meth:`_measure` and a few class attributes.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import ClassVar

from arc_eval_service.evaluators.base import Evaluator, ratio_score, require_number
from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationResult,
    EvaluatorInput,
)


class BudgetEvaluator(Evaluator):
    """Pass when a measured metric stays within a configured budget.

    Subclasses declare ``config_key`` (the required numeric budget), the detail
    labels and a number format, and implement :meth:`_measure` to read the metric
    off the case (raising :class:`~arc_eval_service.core.errors.EvaluationError`
    when the required signal is absent).
    """

    config_key: ClassVar[str]
    value_label: ClassVar[str]
    limit_label: ClassVar[str]
    value_format: ClassVar[str] = ".4f"

    @abstractmethod
    def _measure(self, case: EvaluationCase) -> float:
        """Return the metric to compare against the budget."""
        raise NotImplementedError

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        actual = self._measure(data.case)
        limit = require_number(data.config, self.config_key)
        return EvaluationResult(
            evaluator_name=self.name,
            score=round(ratio_score(limit, actual), 4),
            passed=actual <= limit,
            details={
                self.value_label: format(actual, self.value_format),
                self.limit_label: format(limit, self.value_format),
            },
        )
