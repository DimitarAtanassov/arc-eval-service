"""Unit tests for repository row <-> domain mappers (no database needed)."""

from datetime import UTC, datetime

import pytest

from arc_eval_service.db.models import SpanRow, TraceRow
from arc_eval_service.db.repositories.cases import case_to_row, row_to_stored_case
from arc_eval_service.db.repositories.results import result_to_row, row_to_result
from arc_eval_service.db.repositories.traces import (
    header_to_values,
    row_to_header,
    row_to_span,
    span_to_values,
)
from arc_eval_service.evaluation.schemas import (
    EvaluationCase,
    EvaluationResult,
    StoredCase,
)
from arc_eval_service.traces.schemas import SpanRecord, TraceHeader

pytestmark = pytest.mark.unit


def test_case_round_trips_through_row() -> None:
    stored = StoredCase(
        case_id="c1",
        trace_id="t1",
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
        case=EvaluationCase(
            request_id="r1",
            input="q",
            output="a",
            context=["c"],
            reference="ref",
            metadata={"k": "v"},
        ),
    )
    assert row_to_stored_case(case_to_row(stored)) == stored


def test_result_round_trips_with_assigned_identity() -> None:
    result = EvaluationResult(
        metric="safety",
        model="m",
        score=0.9,
        passed=True,
        label="ok",
        explanation="e",
        latency_ms=5.0,
    )
    row = result_to_row("c1", result)
    assert row.case_id == "c1" and row.result_id
    assert row_to_result(row) == result


def test_span_mappers_round_trip() -> None:
    record = SpanRecord(
        span_id="s1",
        trace_id="t1",
        name="arc.llm.call",
        start_unix_nano=1,
        end_unix_nano=2,
        attributes={"a": "b"},
    )
    row = SpanRow(**span_to_values(record))
    assert row_to_span(row) == record


def test_header_mappers_round_trip() -> None:
    header = TraceHeader(
        trace_id="t1",
        request_id="r1",
        service_name="svc",
        start_unix_nano=1,
        end_unix_nano=2,
    )
    row = TraceRow(**header_to_values(header))
    assert row_to_header(row) == header
