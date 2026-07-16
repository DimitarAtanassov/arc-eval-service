"""Persistence for run items.

A run item is the per-entry link a run writes as it scores: it ties one dataset
entry, evaluated in one run, to the eval_request that holds its metric scores. This
is what lets a run reuse the evaluate persistence and lets aggregation join back to
evaluation_results.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.db.models import RunItemRow
from arc_eval_service.db.records import NewRunItem, StoredRunItem
from arc_eval_service.db.repositories.base import BaseRepository


def new_run_item_to_row(item: NewRunItem) -> RunItemRow:
    """Map a new run item record to its ORM row."""
    return RunItemRow(
        id=item.id,
        run_id=item.run_id,
        dataset_entry_id=item.dataset_entry_id,
        eval_request_id=item.eval_request_id,
        created_at=item.created_at,
    )


def row_to_stored_run_item(row: RunItemRow) -> StoredRunItem:
    """Map a persisted run item row back to a storage record."""
    return StoredRunItem(
        id=row.id,
        run_id=row.run_id,
        dataset_entry_id=row.dataset_entry_id,
        eval_request_id=row.eval_request_id,
        created_at=row.created_at,
    )


class RunItemRepository(BaseRepository):
    """Persistence for run items."""

    async def create_many(
        self, items: list[NewRunItem], *, session: AsyncSession | None = None
    ) -> list[StoredRunItem]:
        """Persist run items, joining a caller's transaction when provided."""
        async with self._write(session) as active:
            active.add_all([new_run_item_to_row(item) for item in items])
        return [StoredRunItem(**item.model_dump()) for item in items]

    async def list_for_run(self, run_id: str) -> list[StoredRunItem]:
        """Return the run items written for one run."""
        stmt = select(RunItemRow).where(RunItemRow.run_id == run_id)
        async with self._read() as session:
            rows = (await session.scalars(stmt)).all()
        return [row_to_stored_run_item(row) for row in rows]
