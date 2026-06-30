"""Unit tests for the Postgres record <-> row mapping (no database needed)."""

from datetime import UTC, datetime

import pytest

from arc_eval_service.schemas.models import (
    EvaluationCase,
    EvaluationRecord,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
    JudgeSpec,
)
from arc_eval_service.storage.evaluation import (
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
                judge="safety",
                model="claude-opus-4-8",
                score=0.9,
                passed=True,
                label="safe",
                explanation="no issues",
                latency_ms=12.5,
            )
        ],
        aggregate_score=0.9,
        passed=True,
        created_at=datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 6, 28, 12, 0, 1, tzinfo=UTC),
        case=EvaluationCase(request_id="r1", output="hello", input="hi"),
        specs=[JudgeSpec(judge="safety", model="default")],
        rerun_of="parent-eval",
    )


def test_record_round_trips_through_row() -> None:
    record = _record()
    restored = row_to_record(record_to_row(record))
    assert restored == record


def test_results_and_specs_serialize_to_json_safe_dicts() -> None:
    row = record_to_row(_record())
    assert row.results[0]["judge"] == "safety"
    assert row.specs[0]["judge"] == "safety"
    assert row.rerun_of == "parent-eval"
    assert row.status == "completed"


def test_apply_record_overwrites_mutable_fields() -> None:
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
