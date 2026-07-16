"""Persistence for an experiment's dataset entries.

One completed interaction per row (input, output, optional system prompt). A run
scores these; nothing here scores. The record <-> row mappers stay pure so they
unit-test without a database.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.db.models import DatasetEntryRow
from arc_eval_service.db.records import NewDatasetEntry, StoredDatasetEntry
from arc_eval_service.db.repositories.base import BaseRepository


def new_dataset_entry_to_row(item: NewDatasetEntry) -> DatasetEntryRow:
    """Map a new dataset entry record to its ORM row."""
    return DatasetEntryRow(
        id=item.id,
        experiment_id=item.experiment_id,
        position=item.position,
        input_text=item.input_text,
        system_text=item.system_text,
        output_text=item.output_text,
        created_at=item.created_at,
    )


def row_to_stored_dataset_entry(row: DatasetEntryRow) -> StoredDatasetEntry:
    """Map a persisted dataset entry row back to a storage record."""
    return StoredDatasetEntry(
        id=row.id,
        experiment_id=row.experiment_id,
        position=row.position,
        input_text=row.input_text,
        system_text=row.system_text,
        output_text=row.output_text,
        created_at=row.created_at,
    )


class DatasetEntryRepository(BaseRepository):
    """Persistence for an experiment's dataset entries."""

    async def create_many(
        self, items: list[NewDatasetEntry], *, session: AsyncSession | None = None
    ) -> list[StoredDatasetEntry]:
        """Persist dataset entries, joining a caller's transaction when provided."""
        async with self._write(session) as active:
            active.add_all([new_dataset_entry_to_row(item) for item in items])
        return [StoredDatasetEntry(**item.model_dump()) for item in items]

    async def list_for_experiment(
        self, experiment_id: str, limit: int
    ) -> list[StoredDatasetEntry]:
        """Return an experiment's dataset entries in position order (bounded)."""
        stmt = (
            select(DatasetEntryRow)
            .where(DatasetEntryRow.experiment_id == experiment_id)
            .order_by(DatasetEntryRow.position)
            .limit(limit)
        )
        async with self._read() as session:
            rows = (await session.scalars(stmt)).all()
        return [row_to_stored_dataset_entry(row) for row in rows]

    async def count_for_experiment(self, experiment_id: str) -> int:
        """Return how many dataset entries an experiment has (also the next position)."""
        stmt = select(func.count()).where(
            DatasetEntryRow.experiment_id == experiment_id
        )
        async with self._read() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def counts_for_experiments(self, experiment_ids: list[str]) -> dict[str, int]:
        """Return the dataset size for each experiment in one grouped query (no N+1)."""
        if not experiment_ids:
            return {}
        stmt = (
            select(DatasetEntryRow.experiment_id, func.count().label("n"))
            .where(DatasetEntryRow.experiment_id.in_(experiment_ids))
            .group_by(DatasetEntryRow.experiment_id)
        )
        async with self._read() as session:
            rows = (await session.execute(stmt)).all()
        counts = {row.experiment_id: int(row.n) for row in rows}
        return {
            experiment_id: counts.get(experiment_id, 0)
            for experiment_id in experiment_ids
        }
