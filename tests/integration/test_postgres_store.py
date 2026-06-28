"""Integration tests for PostgresEvaluationStore using a real Postgres container.

Skips automatically when Docker / testcontainers are unavailable.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.schemas.models import (
    EvaluationRecord,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
)
from arc_eval_service.storage.orm import Base
from arc_eval_service.storage.postgres import PostgresEvaluationStore

pytestmark = pytest.mark.integration

try:
    from testcontainers.postgres import PostgresContainer

    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    if not _HAS_TESTCONTAINERS:
        pytest.skip("testcontainers not installed")
    try:
        with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
            yield container.get_connection_url()
    except Exception as exc:  # docker not running / image pull failed
        pytest.skip(f"Postgres container unavailable: {exc}")


@pytest.fixture
async def store(postgres_url: str) -> AsyncIterator[PostgresEvaluationStore]:
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    backend = PostgresEvaluationStore(postgres_url)
    yield backend
    await backend.dispose()


def _pending(evaluation_id: str, request_id: str) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_id=evaluation_id,
        request_id=request_id,
        status=EvaluationStatus.PENDING,
        mode=ExecutionMode.ASYNC,
        created_at=datetime.now(UTC),
    )


async def test_create_get_update_roundtrip(store: PostgresEvaluationStore):
    record = _pending("e1", "r1")
    await store.create(record)

    fetched = await store.get("e1")
    assert fetched.status is EvaluationStatus.PENDING

    completed = record.model_copy(
        update={
            "status": EvaluationStatus.COMPLETED,
            "results": [
                EvaluationResult(evaluator_name="exact_match", score=1.0, passed=True)
            ],
            "aggregate_score": 1.0,
            "passed": True,
            "completed_at": datetime.now(UTC),
        }
    )
    await store.update(completed)

    again = await store.get("e1")
    assert again.status is EvaluationStatus.COMPLETED
    assert again.passed is True
    assert again.results[0].evaluator_name == "exact_match"


async def test_get_missing_raises_not_found(store: PostgresEvaluationStore):
    with pytest.raises(NotFoundError):
        await store.get("does-not-exist")


async def test_update_missing_raises_not_found(store: PostgresEvaluationStore):
    with pytest.raises(NotFoundError):
        await store.update(_pending("ghost", "r9"))


async def test_list_recent_orders_by_created_at(store: PostgresEvaluationStore):
    older = _pending("old", "r1")
    newer = _pending("new", "r2")
    newer = newer.model_copy(update={"created_at": datetime.now(UTC)})
    await store.create(older)
    await store.create(newer)

    recent = await store.list_recent(limit=10)
    ids = [r.evaluation_id for r in recent]
    assert ids.index("new") < ids.index("old")
