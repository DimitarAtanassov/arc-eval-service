"""Unit tests for pure trace assembly."""

import pytest

from arc_eval_service.traces.schemas import SpanRecord
from arc_eval_service.traces.service import assemble_trace

pytestmark = pytest.mark.unit


def _span(span_id: str, **overrides: object) -> SpanRecord:
    base: dict[str, object] = {
        "span_id": span_id,
        "trace_id": "t1",
        "name": "arc.llm.call",
        "start_unix_nano": 1_000_000_000,
        "end_unix_nano": 1_500_000_000,
        "attributes": {},
    }
    base.update(overrides)
    return SpanRecord.model_validate(base)


def test_assemble_builds_offsets_and_duration() -> None:
    root = _span("root", attributes={"arc.llm.request.model": "gpt-4o"})
    child = _span(
        "child",
        parent_span_id="root",
        name="arc.evaluation.run",
        start_unix_nano=1_200_000_000,
        end_unix_nano=1_400_000_000,
        attributes={"arc.eval.name": "safety"},
    )

    trace = assemble_trace("t1", "req-1", [child, root])

    assert trace.request_id == "req-1" and trace.duration_ms == 500.0
    by_id = {s.span_id: s for s in trace.spans}
    assert by_id["root"].start_offset_ms == 0.0 and by_id["root"].duration_ms == 500.0
    assert by_id["child"].start_offset_ms == 200.0
    assert by_id["child"].duration_ms == 200.0
    assert by_id["root"].attributes["arc.llm.request.model"] == "gpt-4o"
    assert by_id["child"].attributes["arc.eval.name"] == "safety"
