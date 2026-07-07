"""Persistence for evaluation requests: the interactions submitted for scoring.

The repository and its pure ``record -> row`` mapper live together, so "how is an
eval request stored?" is answered in one file. The mapper is a pure function and
unit-tests without a live database.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.db.models import EvalRequestRow
from arc_eval_service.db.records import NewEvalRequest, StoredEvalRequest
from arc_eval_service.db.repositories.base import BaseRepository


def new_request_to_row(item: NewEvalRequest) -> EvalRequestRow:
    """Map a new eval request to its row (``created_at`` is stamped by the database)."""
    return EvalRequestRow(
        id=item.id,
        input_text=item.input_text,
        output_text=item.output_text,
        prompt=item.prompt,
        inference_id=item.inference_id,
        model_id=item.model_id,
        request_metadata=item.request_metadata,
    )


def row_to_stored_request(row: EvalRequestRow) -> StoredEvalRequest:
    """Map a persisted row back to a storage record (pure; unit-tests without a database)."""
    return StoredEvalRequest(
        id=row.id,
        input_text=row.input_text,
        output_text=row.output_text,
        prompt=row.prompt,
        inference_id=row.inference_id,
        model_id=row.model_id,
        request_metadata=row.request_metadata,
        created_at=row.created_at,
    )


class EvalRequestRepository(BaseRepository):
    """Persistence for evaluation requests."""

    async def create(
        self, item: NewEvalRequest, *, session: AsyncSession | None = None
    ) -> None:
        async with self._write(session) as active:
            active.add(new_request_to_row(item))

    async def list_recent(self, limit: int) -> list[StoredEvalRequest]:
        """Return the most recent eval requests, newest first (bounded page size)."""
        stmt = (
            select(EvalRequestRow)
            .order_by(EvalRequestRow.created_at.desc())
            .limit(limit)
        )
        async with self._read() as session:
            rows = (await session.scalars(stmt)).all()
        return [row_to_stored_request(row) for row in rows]

    async def get(self, request_id: str) -> StoredEvalRequest | None:
        """Return one eval request by id, or ``None`` when absent."""
        async with self._read() as session:
            row = await session.get(EvalRequestRow, request_id)
        return row_to_stored_request(row) if row is not None else None
