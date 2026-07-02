"""Persistence for evaluation requests: the interactions submitted for scoring.

The repository and its pure ``record -> row`` mapper live together, so "how is an
eval request stored?" is answered in one file. The mapper is a pure function and
unit-tests without a live database.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.db.models import EvalRequestRow
from arc_eval_service.db.records import NewEvalRequest
from arc_eval_service.db.repositories.base import BaseRepository


def new_request_to_row(item: NewEvalRequest) -> EvalRequestRow:
    """Map a new eval request to its row (``created_at`` is stamped by the database)."""
    return EvalRequestRow(
        id=item.id,
        task_type=item.task_type,
        input_text=item.input_text,
        output_text=item.output_text,
        prompt=item.prompt,
        inference_id=item.inference_id,
        model_id=item.model_id,
        request_metadata=item.request_metadata,
    )


class EvalRequestRepository(BaseRepository):
    """Persistence for evaluation requests."""

    async def create(
        self, item: NewEvalRequest, *, session: AsyncSession | None = None
    ) -> None:
        async with self._write(session) as active:
            active.add(new_request_to_row(item))
