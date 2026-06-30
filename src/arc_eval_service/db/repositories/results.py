"""Persistence for per-metric results, keyed by case.

The :class:`ResultRepository` plus its pure row <-> domain mappers. Results have
no aggregate: one row per metric, replaced wholesale when a case is re-scored.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from arc_eval_service.db.models import ResultRow
from arc_eval_service.db.repositories.base import BaseRepository
from arc_eval_service.evaluation.schemas import EvaluationResult


def result_to_row(case_id: str, result: EvaluationResult) -> ResultRow:
    return ResultRow(
        result_id=str(uuid4()),
        case_id=case_id,
        metric=result.metric,
        model=result.model,
        score=result.score,
        passed=result.passed,
        label=result.label,
        explanation=result.explanation,
        latency_ms=result.latency_ms,
        error=result.error,
        created_at=datetime.now(UTC),
    )


def row_to_result(row: ResultRow) -> EvaluationResult:
    return EvaluationResult(
        metric=row.metric,
        model=row.model,
        score=row.score,
        passed=row.passed,
        label=row.label,
        explanation=row.explanation,
        latency_ms=row.latency_ms,
        error=row.error,
    )


class ResultRepository(BaseRepository):
    """Persistence for per-metric results, keyed by case."""

    async def set_for_case(self, case_id: str, results: list[EvaluationResult]) -> None:
        """Replace a case's results (delete then insert) in one transaction."""
        async with self._transaction() as session:
            await session.execute(delete(ResultRow).where(ResultRow.case_id == case_id))
            session.add_all([result_to_row(case_id, r) for r in results])

    async def get_for_case(self, case_id: str) -> list[EvaluationResult]:
        stmt = (
            select(ResultRow)
            .where(ResultRow.case_id == case_id)
            .order_by(ResultRow.created_at)
        )
        async with self._session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [row_to_result(row) for row in rows]

    async def get_for_cases(
        self, case_ids: list[str]
    ) -> dict[str, list[EvaluationResult]]:
        """Batch-fetch results for many cases (avoids an N+1 over a listing)."""
        grouped: dict[str, list[EvaluationResult]] = {cid: [] for cid in case_ids}
        if not case_ids:
            return grouped
        stmt = (
            select(ResultRow)
            .where(ResultRow.case_id.in_(case_ids))
            .order_by(ResultRow.created_at)
        )
        async with self._session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            grouped[row.case_id].append(row_to_result(row))
        return grouped
