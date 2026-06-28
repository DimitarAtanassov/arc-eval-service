"""Regex evaluator: output must match a configured pattern."""

from __future__ import annotations

import re
from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.base import (
    Evaluator,
    optional_bool,
    optional_str,
    require_str,
)
from arc_eval_service.schemas.models import EvaluationResult, EvaluatorInput


class RegexEvaluator(Evaluator):
    """Pass when ``output`` matches the configured regular expression.

    Config:
        ``pattern`` (str, required)
        ``mode`` (str, default "search"): one of "search" or "fullmatch".
        ``case_sensitive`` (bool, default True)
    """

    name: ClassVar[str] = "regex"
    description: ClassVar[str] = "Output must match a configured regular expression."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        case = data.case
        if case.output is None:
            raise EvaluationError("regex requires 'output'")

        pattern = require_str(data.config, "pattern")
        mode = optional_str(data.config, "mode", "search")
        if mode not in {"search", "fullmatch"}:
            raise EvaluationError("regex 'mode' must be 'search' or 'fullmatch'")
        case_sensitive = optional_bool(data.config, "case_sensitive", default=True)

        flags = re.NOFLAG if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            raise EvaluationError(f"invalid regex pattern: {exc}") from exc

        match = (
            compiled.fullmatch(case.output)
            if mode == "fullmatch"
            else compiled.search(case.output)
        )
        matched = match is not None
        return EvaluationResult(
            evaluator_name=self.name,
            score=1.0 if matched else 0.0,
            passed=matched,
            details={"matched": str(matched).lower(), "mode": mode},
        )
