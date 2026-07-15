from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from arc_eval_service.db.engine import Database
from arc_eval_service.db.models import ExperimentRow
from arc_eval_service.db.records import (
    NewDatasetEntry,
    NewExperiment,
    NewExperimentRun,
    NewRunItem,
)
from arc_eval_service.db.repositories import (
    DatasetEntryRepository,
    ExperimentRepository,
    ExperimentRunRepository,
    RunItemRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(clean_db: str) -> AsyncIterator[Database]:
    db = Database(clean_db)
    yield db
    await db.dispose()


def _experiment(exp_id: str = "exp-1", name: str = "baseline") -> NewExperiment:
    return NewExperiment(
        id=exp_id,
        name=name,
        description=None,
        metrics=["faithfulness"],
        created_at=datetime.now(UTC),
    )


def _entry(
    entry_id: str, exp_id: str, position: int, *, system_text: str | None = None
) -> NewDatasetEntry:
    return NewDatasetEntry(
        id=entry_id,
        experiment_id=exp_id,
        position=position,
        input_text=f"input-{position}",
        system_text=system_text,
        output_text=f"output-{position}",
        created_at=datetime.now(UTC),
    )


async def test_dataset_entries_persist_and_list_in_position_order(
    database: Database,
) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    entries = DatasetEntryRepository(database.sessionmaker)
    await experiments.create(_experiment())

    # Insert out of position order to prove the list orders by position, not insert.
    await entries.create_many(
        [_entry("e2", "exp-1", 1), _entry("e1", "exp-1", 0, system_text="be precise")]
    )

    listed = await entries.list_for_experiment("exp-1", limit=10)

    assert [entry.id for entry in listed] == ["e1", "e2"]
    assert listed[0].system_text == "be precise"
    assert listed[1].system_text is None


async def test_count_for_experiment_returns_dataset_size(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    entries = DatasetEntryRepository(database.sessionmaker)
    await experiments.create(_experiment())
    assert await entries.count_for_experiment("exp-1") == 0

    await entries.create_many([_entry("e1", "exp-1", 0), _entry("e2", "exp-1", 1)])

    assert await entries.count_for_experiment("exp-1") == 2


async def test_run_items_link_entries_to_a_run(database: Database) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    entries = DatasetEntryRepository(database.sessionmaker)
    runs = ExperimentRunRepository(database.sessionmaker)
    items = RunItemRepository(database.sessionmaker)
    await experiments.create(_experiment())
    await entries.create_many([_entry("e1", "exp-1", 0)])
    await runs.create(
        NewExperimentRun(
            id="run-1",
            experiment_id="exp-1",
            status="completed",
            created_at=datetime.now(UTC),
        )
    )

    await items.create_many(
        [
            NewRunItem(
                id="ri-1",
                run_id="run-1",
                dataset_entry_id="e1",
                eval_request_id=None,
                created_at=datetime.now(UTC),
            )
        ]
    )

    listed = await items.list_for_run("run-1")

    assert [item.dataset_entry_id for item in listed] == ["e1"]


async def test_deleting_an_experiment_cascades_to_its_dataset(
    database: Database,
) -> None:
    experiments = ExperimentRepository(database.sessionmaker)
    entries = DatasetEntryRepository(database.sessionmaker)
    await experiments.create(_experiment())
    await entries.create_many([_entry("e1", "exp-1", 0)])

    async with database.sessionmaker() as session, session.begin():
        row = await session.get(ExperimentRow, "exp-1")
        await session.delete(row)

    assert await entries.count_for_experiment("exp-1") == 0
