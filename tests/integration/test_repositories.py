"""Integration tests for repositories against a real Postgres container."""

from collections.abc import AsyncIterator

import pytest

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import (
    EvalInputRepository,
    PromptTemplateRepository,
)
from arc_eval_service.ingestion.schemas import NewEvalInput

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(clean_db: str) -> AsyncIterator[Database]:
    db = Database(clean_db)
    yield db
    await db.dispose()


async def test_get_or_create_deduplicates_by_content(database: Database) -> None:
    repo = PromptTemplateRepository(database.sessionmaker)
    first = await repo.get_or_create("Answer: {q}")
    second = await repo.get_or_create("Answer: {q}")
    third = await repo.get_or_create("Different: {q}")
    assert first == second
    assert first != third


async def test_create_then_get_eval_input(database: Database) -> None:
    templates = PromptTemplateRepository(database.sessionmaker)
    inputs = EvalInputRepository(database.sessionmaker)

    template_id = await templates.get_or_create("P: {a}")
    new = NewEvalInput(
        id="ei-1",
        prompt_template_id=template_id,
        template_context={"a": "x"},
        rendered_prompt="P: x",
        system_message=None,
        llm_response={"content": "y"},
        llm_config={"model": "m"},
    )
    await inputs.create(new)

    stored = await inputs.get("ei-1")
    assert stored.id == "ei-1"
    assert stored.prompt_template_id == template_id
    assert stored.rendered_prompt == "P: x"
    assert stored.created_at is not None


async def test_get_missing_eval_input_raises(database: Database) -> None:
    inputs = EvalInputRepository(database.sessionmaker)
    with pytest.raises(NotFoundError):
        await inputs.get("does-not-exist")
