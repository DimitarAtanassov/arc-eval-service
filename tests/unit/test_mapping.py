"""Unit tests for pure OTLP -> domain mapping."""

import pytest

from arc_eval_service.traces.mapping import (
    build_trace_headers,
    parse_spans,
    spans_to_cases,
)
from arc_eval_service.traces.wire import OTLPTracePayload

pytestmark = pytest.mark.unit


def _payload(**span: object) -> OTLPTracePayload:
    base: dict[str, object] = {"name": "arc.llm.call", "traceId": "t1", "spanId": "s1"}
    base.update(span)
    return OTLPTracePayload.model_validate(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "demo"}}
                        ]
                    },
                    "scopeSpans": [{"spans": [base]}],
                }
            ]
        }
    )


def test_parse_spans_normalises_identity_and_timing() -> None:
    payload = _payload(
        startTimeUnixNano="1000000000",
        endTimeUnixNano="1500000000",
        kind=3,
        attributes=[{"key": "arc.request_id", "value": {"stringValue": "req-1"}}],
    )
    [rec] = parse_spans(payload)
    assert rec.span_id == "s1" and rec.trace_id == "t1"
    assert rec.service_name == "demo" and rec.kind == "client"
    assert rec.start_unix_nano == 1000000000
    assert rec.attributes["arc.request_id"] == "req-1"


def test_parse_spans_skips_unaddressable() -> None:
    payload = OTLPTracePayload.model_validate(
        {"resourceSpans": [{"scopeSpans": [{"spans": [{"name": "x"}]}]}]}
    )
    assert parse_spans(payload) == []


def test_build_trace_headers_aggregates_timing_and_request_id() -> None:
    payload = _payload(
        startTimeUnixNano="1000000000",
        endTimeUnixNano="1500000000",
        attributes=[{"key": "arc.request_id", "value": {"stringValue": "req-1"}}],
    )
    [header] = build_trace_headers(parse_spans(payload))
    assert header.trace_id == "t1" and header.request_id == "req-1"
    assert header.service_name == "demo"
    assert header.start_unix_nano == 1000000000
    assert header.end_unix_nano == 1500000000


def test_spans_to_cases_extracts_io() -> None:
    payload = _payload(
        attributes=[
            {"key": "arc.request_id", "value": {"stringValue": "req-1"}},
            {"key": "arc.llm.request.model", "value": {"stringValue": "gpt-x"}},
        ],
        events=[
            {
                "name": "arc.llm.message",
                "attributes": [
                    {"key": "arc.llm.message.role", "value": {"stringValue": "user"}},
                    {"key": "arc.llm.message.content", "value": {"stringValue": "Q?"}},
                ],
            },
            {
                "name": "arc.llm.choice",
                "attributes": [
                    {"key": "arc.llm.message.content", "value": {"stringValue": "A"}}
                ],
            },
        ],
    )
    [case] = spans_to_cases(payload)
    assert case.request_id == "req-1" and case.input == "Q?" and case.output == "A"
    assert case.metadata["model"] == "gpt-x" and case.metadata["trace_id"] == "t1"


def test_spans_to_cases_skips_self_service() -> None:
    payload = _payload(
        events=[
            {
                "name": "arc.llm.choice",
                "attributes": [
                    {"key": "arc.llm.message.content", "value": {"stringValue": "A"}}
                ],
            }
        ]
    )
    assert spans_to_cases(payload, self_service_name="demo") == []


def test_spans_without_choice_are_not_evaluable() -> None:
    assert spans_to_cases(_payload()) == []
