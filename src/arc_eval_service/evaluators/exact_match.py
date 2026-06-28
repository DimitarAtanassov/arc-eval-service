"""Exact-match evaluator: output must equal the reference text."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.base import Evaluator, optional_bool
from arc_eval_service.schemas.models import EvaluationResult, EvaluatorInput


class ExactMatchEvaluator(Evaluator):
    """Pass when ``output`` exactly equals ``reference``.

    Config:
        ``case_sensitive`` (bool, default True)
        ``strip`` (bool, default True): trim surrounding whitespace before compare.
    """

    name: ClassVar[str] = "exact_match"
    description: ClassVar[str] = "Output must exactly equal the reference text."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        case = data.case
        if case.output is None:
            raise EvaluationError("exact_match requires 'output'")
        if case.reference is None:
            raise EvaluationError("exact_match requires 'reference'")

        case_sensitive = optional_bool(data.config, "case_sensitive", default=True)
        strip = optional_bool(data.config, "strip", default=True)

        actual = case.output
        expected = case.reference
        if strip:
            actual, expected = actual.strip(), expected.strip()
        if not case_sensitive:
            actual, expected = actual.casefold(), expected.casefold()

        matched = actual == expected
        return EvaluationResult(
            evaluator_name=self.name,
            score=1.0 if matched else 0.0,
            passed=matched,
            details={"matched": str(matched).lower()},
        )
