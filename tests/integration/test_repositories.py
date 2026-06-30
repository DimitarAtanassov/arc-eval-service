"""Integration tests for repositories against a real Postgres container."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import (
    CaseRepository,
    ResultRepository,
    TraceRepository,
)
from arc_eval_service.evaluation.schemas import (
    EvaluationCase,
    EvaluationResult,
    StoredCase,
)
from arc_eval_service.traces.schemas import SpanRecord, TraceHeader

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(clean_db: str) -> AsyncIterator[Database]:
    db = Database(clean_db)
    yield db
    await db.dispose()


def _stored(
    case_id: str, *, request_id: str = "r1", trace_id: str | None = None
) -> StoredCase:
    return StoredCase(
        case_id=case_id,
        trace_id=trace_id,
        created_at=datetime.now(UTC),
        case=EvaluationCase(request_id=request_id, output="hi"),
    )


async def test_case_create_get_delete(database: Database) -> None:
    cases = CaseRepository(database.sessionmaker)
    await cases.create(_stored("c1", trace_id="t1"))
    fetched = await cases.get("c1")
    assert fetched.case_id == "c1" and fetched.trace_id == "t1"
    assert fetched.case.output == "hi"
    await cases.delete("c1")
    with pytest.raises(NotFoundError):
        await cases.get("c1")


async def test_get_unknown_case_raises(database: Database) -> None:
    with pytest.raises(NotFoundError):
        await CaseRepository(database.sessionmaker).get("missing")


async def test_results_replace_and_cascade_on_case_delete(database: Database) -> None:
    cases = CaseRepository(database.sessionmaker)
    results = ResultRepository(database.sessionmaker)
    await cases.create(_stored("c1"))
    await results.set_for_case(
        "c1", [EvaluationResult(metric="safety", score=0.9, passed=True)]
    )
    await results.set_for_case(
        "c1",
        [
            EvaluationResult(metric="safety", score=0.4, passed=False),
            EvaluationResult(metric="custom", score=1.0, passed=True),
        ],
    )
    got = await results.get_for_case("c1")
    assert {r.metric for r in got} == {"safety", "custom"}
    assert next(r for r in got if r.metric == "safety").score == 0.4

    await cases.delete("c1")
    assert await results.get_for_case("c1") == []


async def test_get_for_cases_batches(database: Database) -> None:
    cases = CaseRepository(database.sessionmaker)
    results = ResultRepository(database.sessionmaker)
    await cases.create(_stored("c1"))
    await cases.create(_stored("c2"))
    await results.set_for_case(
        "c1", [EvaluationResult(metric="safety", score=1.0, passed=True)]
    )
    grouped = await results.get_for_cases(["c1", "c2"])
    assert len(grouped["c1"]) == 1 and grouped["c2"] == []


async def test_list_recent_orders_by_created_desc(database: Database) -> None:
    cases = CaseRepository(database.sessionmaker)
    await cases.create(
        StoredCase(
            case_id="old",
            trace_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            case=EvaluationCase(request_id="r", output="a"),
        )
    )
    await cases.create(
        StoredCase(
            case_id="new",
            trace_id=None,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            case=EvaluationCase(request_id="r", output="b"),
        )
    )
    recent = await cases.list_recent(10)
    assert [c.case_id for c in recent[:2]] == ["new", "old"]


async def test_trace_upsert_is_idempotent_and_readable(database: Database) -> None:
    traces = TraceRepository(database.sessionmaker)
    spans = [
        SpanRecord(
            span_id="s1",
            trace_id="t1",
            name="arc.llm.call",
            start_unix_nano=1000,
            end_unix_nano=2000,
            attributes={"k": "v"},
        )
    ]
    await traces.upsert_headers(
        [
            TraceHeader(
                trace_id="t1",
                request_id="req-1",
                service_name="svc",
                start_unix_nano=1000,
                end_unix_nano=2000,
            )
        ]
    )
    await traces.upsert_spans(spans)
    await traces.upsert_spans(spans)  # redelivery must not duplicate

    header = await traces.get_header("t1")
    assert header is not None and header.request_id == "req-1"
    got = await traces.get_spans("t1")
    assert len(got) == 1 and got[0].span_id == "s1"
