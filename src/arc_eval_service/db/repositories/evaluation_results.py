"""Persistence for evaluation results: one metric score per row.

The repository writes results in a single transaction (all metrics for one
request land together) and keeps its ``record -> row`` mapper pure and local, so
it unit-tests without a live database.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.db.models import EvaluationResultRow
from arc_eval_service.db.records import NewEvaluationResult, StoredEvaluationResult
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


def row_to_stored_result(row: EvaluationResultRow) -> StoredEvaluationResult:
    """Map a persisted row back to a storage record (pure; unit-tests without a database)."""
    return StoredEvaluationResult(
        id=row.id,
        eval_request_id=row.eval_request_id,
        inference_id=row.inference_id,
        model_id=row.model_id,
        metric_name=row.metric_name,
        score=row.score,
        passed=row.passed,
        reasoning=row.reasoning,
        evaluator_name=row.evaluator_name,
        evaluator_version=row.evaluator_version,
        judge=row.judge,
        prompt=row.prompt,
        latency_ms=row.latency_ms,
        error=row.error,
        created_at=row.created_at,
    )


class EvaluationResultRepository(BaseRepository):
    """Persistence for evaluation results."""

    async def create_many(
        self,
        items: Sequence[NewEvaluationResult],
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Persist all results for one request, joining a caller's transaction."""
        if not items:
            return
        async with self._write(session) as active:
            active.add_all([new_result_to_row(item) for item in items])

    async def list_recent(
        self,
        limit: int,
        *,
        metric_name: str | None = None,
        model_id: str | None = None,
    ) -> list[StoredEvaluationResult]:
        """Return recent metric scores, newest first, optionally filtered.

        Both filters are exact matches on indexed columns (``metric_name``,
        ``model_id``); either may be omitted. ``limit`` bounds the page size.
        """
        stmt = select(EvaluationResultRow)
        if metric_name is not None:
            stmt = stmt.where(EvaluationResultRow.metric_name == metric_name)
        if model_id is not None:
            stmt = stmt.where(EvaluationResultRow.model_id == model_id)
        stmt = stmt.order_by(EvaluationResultRow.created_at.desc()).limit(limit)
        async with self._read() as session:
            rows = (await session.scalars(stmt)).all()
        return [row_to_stored_result(row) for row in rows]

    async def list_for_request(self, request_id: str) -> list[StoredEvaluationResult]:
        """Return every metric score for one request, ordered by metric name."""
        stmt = (
            select(EvaluationResultRow)
            .where(EvaluationResultRow.eval_request_id == request_id)
            .order_by(EvaluationResultRow.metric_name)
        )
        async with self._read() as session:
            rows = (await session.scalars(stmt)).all()
        return [row_to_stored_result(row) for row in rows]
