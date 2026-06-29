"""Unit tests for OTel offline ingestion (pure span-event -> case mapping)."""

import pytest

from arc_eval_service.ingest.otlp import OTLPTracePayload, spans_to_cases

pytestmark = pytest.mark.unit


def _attr(key: str, value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": value}}


def _message_event(role: str, content: str) -> dict[str, object]:
    return {
        "name": "arc.llm.message",
        "attributes": [
            _attr("arc.llm.message.role", role),
            _attr("arc.llm.message.content", content),
        ],
    }


def _choice_event(content: str) -> dict[str, object]:
    return {
        "name": "arc.llm.choice",
        "attributes": [
            _attr("arc.llm.message.role", "assistant"),
            _attr("arc.llm.message.content", content),
        ],
    }


def _payload(spans: list[dict[str, object]]) -> OTLPTracePayload:
    return OTLPTracePayload.model_validate(
        {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}
    )


def test_maps_message_and_choice_events_to_case() -> None:
    payload = _payload(
        [
            {
                "name": "arc.llm.call",
                "traceId": "abc123",
                "attributes": [
                    _attr("arc.request_id", "req-1"),
                    _attr("arc.llm.request.model", "gpt-4o"),
                ],
                "events": [
                    _message_event("system", "You are helpful."),
                    _message_event("user", "What is 2+2?"),
                    _choice_event("4"),
                ],
            }
        ]
    )
    cases = spans_to_cases(payload)
    assert len(cases) == 1
    case = cases[0]
    assert case.request_id == "req-1"
    assert case.input == "What is 2+2?"  # the user message
    assert case.output == "4"  # the choice
    assert case.metadata["model"] == "gpt-4o"
    assert case.metadata["trace_id"] == "abc123"


def test_skips_spans_without_a_choice() -> None:
    payload = _payload(
        [{"name": "arc.llm.call", "events": [_message_event("user", "hi")]}]
    )
    assert spans_to_cases(payload) == []


def test_ignores_non_llm_spans() -> None:
    payload = _payload([{"name": "arc.gateway.infer", "events": [_choice_event("x")]}])
    assert spans_to_cases(payload) == []


def test_falls_back_to_trace_id_for_request_id() -> None:
    payload = _payload(
        [
            {
                "name": "arc.llm.call",
                "traceId": "trace-xyz",
                "events": [_choice_event("answer")],
            }
        ]
    )
    cases = spans_to_cases(payload)
    assert cases[0].request_id == "trace-xyz"
    assert cases[0].output == "answer"
