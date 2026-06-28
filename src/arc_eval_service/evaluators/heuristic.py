"""Heuristic evaluator: graded score over simple response-quality checks."""

from __future__ import annotations

from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.evaluators.base import (
    Evaluator,
    clamp01,
    optional_bool,
    optional_number,
    optional_str,
)
from arc_eval_service.schemas.models import EvaluationResult, EvaluatorInput

_DEFAULT_REFUSALS = ("i cannot", "i can't", "i am unable", "as an ai")


class HeuristicEvaluator(Evaluator):
    """Score ``output`` against lightweight quality heuristics.

    The score is the fraction of enabled checks that pass; ``passed`` is true when
    the score meets ``pass_threshold``.

    Config:
        ``min_length`` (number, default 1): minimum character length.
        ``max_length`` (number, optional): maximum character length.
        ``forbid_refusal`` (bool, default False): penalise refusal phrasing.
        ``banned_substring`` (str, optional): output must not contain this text.
        ``pass_threshold`` (number, default 1.0): fraction of checks to pass.
    """

    name: ClassVar[str] = "heuristic"
    description: ClassVar[str] = "Graded score over simple response-quality checks."

    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        case = data.case
        if case.output is None:
            raise EvaluationError("heuristic requires 'output'")

        output = case.output
        checks = self._run_checks(output, data)

        passed_count = sum(1 for ok in checks.values() if ok)
        score = clamp01(passed_count / len(checks)) if checks else 0.0
        threshold = optional_number(data.config, "pass_threshold", 1.0)
        assert threshold is not None  # noqa: S101 - default makes None impossible

        details = {name: str(ok).lower() for name, ok in checks.items()}
        details["score_fraction"] = f"{passed_count}/{len(checks)}"
        return EvaluationResult(
            evaluator_name=self.name,
            score=round(score, 4),
            passed=score >= threshold,
            details=details,
        )

    def _run_checks(self, output: str, data: EvaluatorInput) -> dict[str, bool]:
        min_length = optional_number(data.config, "min_length", 1.0)
        max_length = optional_number(data.config, "max_length", None)
        forbid_refusal = optional_bool(data.config, "forbid_refusal", default=False)
        banned = optional_str(data.config, "banned_substring", "")

        checks: dict[str, bool] = {}
        if min_length is not None:
            checks["min_length"] = len(output) >= int(min_length)
        if max_length is not None:
            checks["max_length"] = len(output) <= int(max_length)
        if forbid_refusal:
            lowered = output.casefold()
            checks["no_refusal"] = not any(p in lowered for p in _DEFAULT_REFUSALS)
        if banned:
            checks["no_banned_substring"] = banned not in output
        if not checks:
            # Always have at least one check so the score is well defined.
            checks["non_empty"] = bool(output.strip())
        return checks
