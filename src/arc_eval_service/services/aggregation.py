"""Pure aggregation of per-judge results into a record-level outcome."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from arc_eval_service.schemas.models import EvaluationResult, EvaluationStatus


@dataclass(frozen=True, slots=True)
class AggregateOutcome:
    """The record-level outcome derived from the per-judge results."""

    status: EvaluationStatus
    aggregate_score: float | None
    passed: bool


def aggregate_results(results: list[EvaluationResult]) -> AggregateOutcome:
    """Derive status, mean score and pass from the scored (non-errored) results.

    A request COMPLETES when at least one judge scored; it is FAILED only when
    every judge errored. ``passed`` requires all scored judges to pass.
    """
    scored = [r for r in results if r.error is None]
    aggregate = round(fmean(r.score for r in scored), 4) if scored else None
    passed = bool(scored) and all(r.passed for r in scored)
    status = EvaluationStatus.COMPLETED if scored else EvaluationStatus.FAILED
    return AggregateOutcome(status=status, aggregate_score=aggregate, passed=passed)
