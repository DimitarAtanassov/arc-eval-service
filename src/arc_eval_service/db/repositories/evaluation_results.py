"""Persistence for evaluation results: one metric score per row.

The repository writes results in a single transaction (all metrics for one
request land together) and keeps its ``record -> row`` mapper pure and local, so
it unit-tests without a live database.
"""

from __future__ import annotations

from collections.abc import Sequence

from arc_eval_service.db.models import EvaluationResultRow
from arc_eval_service.db.records import NewEvaluationResult
from arc_eval_service.db.repositories.base import BaseRepository


def new_result_to_row(item: NewEvaluationResult) -> EvaluationResultRow:
    """Map a new evaluation result to its row (``created_at`` is stamped by the database)."""
    return EvaluationResultRow(
        id=item.id,
        eval_request_id=item.eval_request_id,
        inference_id=item.inference_id,
        model_id=item.model_id,
        metric_name=item.metric_name,
        score=item.score,
        passed=item.passed,
        reasoning=item.reasoning,
        evaluator_name=item.evaluator_name,
        evaluator_version=item.evaluator_version,
        judge=item.judge,
        prompt=item.prompt,
        latency_ms=item.latency_ms,
        error=item.error,
    )


class EvaluationResultRepository(BaseRepository):
    """Persistence for evaluation results."""

    async def create_many(self, items: Sequence[NewEvaluationResult]) -> None:
        """Persist all results for one request in a single transaction."""
        if not items:
            return
        async with self._transaction() as session:
            session.add_all([new_result_to_row(item) for item in items])
