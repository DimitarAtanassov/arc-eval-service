"""Integration tests for repositories against a real Postgres container."""

from collections.abc import AsyncIterator

import pytest

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import EvalInputRepository
from arc_eval_service.ingestion.schemas import NewEvalInput

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(clean_db: str) -> AsyncIterator[Database]:
    db = Database(clean_db)
    yield db
    await db.dispose()


async def test_create_then_get_eval_input(database: Database) -> None:
    inputs = EvalInputRepository(database.sessionmaker)

    new = NewEvalInput(
        id="ei-1",
        rendered_prompt="P: x",
        system_message=None,
        response={"content": "y"},
        config={"model": "m"},
    )
    await inputs.create(new)

    stored = await inputs.get("ei-1")
    assert stored.id == "ei-1"
    assert stored.rendered_prompt == "P: x"
    assert stored.response == {"content": "y"}
    assert stored.config == {"model": "m"}
    assert stored.created_at is not None


async def test_get_missing_eval_input_raises(database: Database) -> None:
    inputs = EvalInputRepository(database.sessionmaker)
    with pytest.raises(NotFoundError):
        await inputs.get("does-not-exist")
