"""Persistence for eval inputs: the LLM interactions to be evaluated.

The repository plus its pure row <-> domain mappers live together, so "how is an
eval input stored?" is answered in one file. The mappers are pure functions and
unit-test without a live database.
"""

from __future__ import annotations

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.db.models import EvalInputRow
from arc_eval_service.db.repositories.base import BaseRepository
from arc_eval_service.ingestion.schemas import EvalInput, NewEvalInput


def new_input_to_row(item: NewEvalInput) -> EvalInputRow:
    """Map a new eval input to its row (``created_at`` is stamped by the database)."""
    return EvalInputRow(
        id=item.id,
        rendered_prompt=item.rendered_prompt,
        system_message=item.system_message,
        model_response=item.response,
        model_config=item.config,
    )


def row_to_input(row: EvalInputRow) -> EvalInput:
    """Map an eval-input row back to its domain model."""
    return EvalInput(
        id=row.id,
        rendered_prompt=row.rendered_prompt,
        system_message=row.system_message,
        response=row.model_response,
        config=row.model_config,
        created_at=row.created_at,
    )


class EvalInputRepository(BaseRepository):
    """Persistence for eval inputs."""

    async def create(self, item: NewEvalInput) -> None:
        async with self._transaction() as session:
            session.add(new_input_to_row(item))

    async def get(self, input_id: str) -> EvalInput:
        async with self._session() as session:
            row = await session.get(EvalInputRow, input_id)
        if row is None:
            raise NotFoundError("eval_input", input_id)
        return row_to_input(row)
