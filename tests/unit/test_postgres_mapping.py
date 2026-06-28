"""Unit tests for the Postgres record <-> row mapping (no database needed)."""

from datetime import UTC, datetime

import pytest

from arc_eval_service.schemas.models import (
    EvaluationRecord,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
)
from arc_eval_service.storage.postgres import (
    apply_record,
    record_to_row,
    row_to_record,
)

pytestmark = pytest.mark.unit


def _record() -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_id="e1",
        request_id="r1",
        status=EvaluationStatus.COMPLETED,
        mode=ExecutionMode.SYNC,
        results=[
            EvaluationResult(
                evaluator_name="exact_match",
                score=1.0,
                passed=True,
                latency_ms=0.5,
                details={"matched": "true"},
            )
        ],
        aggregate_score=1.0,
        passed=True,
        created_at=datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 6, 28, 12, 0, 1, tzinfo=UTC),
    )


def test_record_round_trips_through_row():
    record = _record()
    restored = row_to_record(record_to_row(record))
    assert restored == record


def test_results_serialize_to_json_safe_dicts():
    row = record_to_row(_record())
    assert isinstance(row.results, list)
    assert row.results[0]["evaluator_name"] == "exact_match"
    assert row.status == "completed"
    assert row.mode == "sync"


def test_apply_record_overwrites_mutable_fields():
    original = _record()
    row = record_to_row(original)
    updated = original.model_copy(
        update={
            "status": EvaluationStatus.FAILED,
            "aggregate_score": 0.0,
            "passed": False,
            "results": [],
        }
    )
    apply_record(updated, row)
    assert row.status == "failed"
    assert row.aggregate_score == 0.0
    assert row.passed is False
    assert row.results == []
