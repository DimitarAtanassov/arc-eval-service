"""Unit tests for the span store and pure trace assembly."""

import pytest

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.schemas.models import SpanRecord
from arc_eval_service.services.traces import TraceService, assemble_trace
from arc_eval_service.storage.spans import InMemorySpanStore

pytestmark = pytest.mark.unit


def _span(span_id: str, **overrides: object) -> SpanRecord:
    base: dict[str, object] = {
        "span_id": span_id,
        "trace_id": "trace-1",
        "name": "arc.llm.call",
        "start_unix_nano": 1_000_000_000,
        "end_unix_nano": 1_500_000_000,
        "attributes": {},
    }
    base.update(overrides)
    return SpanRecord.model_validate(base)


def test_assemble_trace_builds_offsets_and_carries_attributes() -> None:
    root = _span(
        "root",
        attributes={"arc.request_id": "req-1", "arc.llm.request.model": "gpt-4o"},
    )
    child = _span(
        "child",
        parent_span_id="root",
        name="arc.evaluation.run",
        start_unix_nano=1_200_000_000,
        end_unix_nano=1_400_000_000,
        attributes={"arc.eval.name": "safety", "arc.eval.score": "0.9"},
    )

    trace = assemble_trace("trace-1", [child, root])

    assert trace.request_id == "req-1"
    assert trace.duration_ms == 500.0
    by_id = {s.span_id: s for s in trace.spans}
    assert by_id["root"].start_offset_ms == 0.0
    assert by_id["root"].duration_ms == 500.0
    assert by_id["child"].start_offset_ms == 200.0
    assert by_id["child"].duration_ms == 200.0
    # both inference and evaluation attributes survive to the UI contract
    assert by_id["root"].attributes["arc.llm.request.model"] == "gpt-4o"
    assert by_id["child"].attributes["arc.eval.name"] == "safety"


async def test_inmemory_store_upsert_is_idempotent_on_span_id() -> None:
    store = InMemorySpanStore()
    await store.upsert_many([_span("s1", name="first")])
    await store.upsert_many([_span("s1", name="second"), _span("s2")])

    spans = await store.get_trace("trace-1")
    assert {s.span_id for s in spans} == {"s1", "s2"}
    assert next(s for s in spans if s.span_id == "s1").name == "second"


async def test_trace_service_raises_when_trace_unknown() -> None:
    service = TraceService(InMemorySpanStore())
    with pytest.raises(NotFoundError):
        await service.get_trace("missing")
