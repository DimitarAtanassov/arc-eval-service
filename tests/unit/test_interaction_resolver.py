"""Unit tests for the interaction resolver: inline passthrough and id resolution."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arc_eval_service.api.schemas import EvaluateRequest, EvaluationMetadata
from arc_eval_service.clients.lab_inference_client import InferenceResult
from arc_eval_service.domain.errors import (
    InferenceNotFoundError,
    LabNotConfiguredError,
)
from arc_eval_service.services.interaction_resolver import InteractionResolver

pytestmark = pytest.mark.unit


def _inference() -> InferenceResult:
    return InferenceResult(
        id="inf-9",
        model_id="mdl-9",
        input_text="the fetched source",
        prompt="Summarize:",
        output_text="the fetched output",
        latency_ms=12,
        prompt_tokens=5,
        completion_tokens=3,
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
    )


class _FakeReader:
    def __init__(self, result: InferenceResult) -> None:
        self._result = result
        self.calls: list[str] = []

    async def get_inference(
        self, inference_id: str, *, correlation_id: str | None = None
    ) -> InferenceResult:
        self.calls.append(inference_id)
        return self._result


class _MissingReader:
    async def get_inference(
        self, inference_id: str, *, correlation_id: str | None = None
    ) -> InferenceResult:
        raise InferenceNotFoundError(inference_id)


async def test_inline_request_is_resolved_without_the_lab() -> None:
    resolver = InteractionResolver(reader=None)
    request = EvaluateRequest.model_validate(
        {
            "input_text": "src",
            "output_text": "out",
            "prompt": "Summarize:",
            "metrics": ["faithfulness"],
            "metadata": {"inference_id": "inf-1"},
        }
    )

    interaction = await resolver.resolve(request)

    assert interaction.input_text == "src"
    assert interaction.output_text == "out"
    assert interaction.metrics == ("faithfulness",)
    assert interaction.metadata.inference_id == "inf-1"


async def test_reference_request_fetches_and_uses_the_inference() -> None:
    reader = _FakeReader(_inference())
    resolver = InteractionResolver(reader)
    request = EvaluateRequest.model_validate(
        {"inference_id": "req-key", "metrics": ["faithfulness"]}
    )

    interaction = await resolver.resolve(request, correlation_id="cid-1")

    assert reader.calls == ["req-key"]
    # The fetched inference is authoritative: its text and ids fill the interaction.
    assert interaction.input_text == "the fetched source"
    assert interaction.output_text == "the fetched output"
    assert interaction.prompt == "Summarize:"
    assert interaction.metadata.inference_id == "inf-9"
    assert interaction.metadata.model_id == "mdl-9"


async def test_reference_request_without_a_lab_raises_not_configured() -> None:
    resolver = InteractionResolver(reader=None)
    request = EvaluateRequest.model_validate(
        {"inference_id": "req-key", "metrics": ["faithfulness"]}
    )
    with pytest.raises(LabNotConfiguredError):
        await resolver.resolve(request)


async def test_reference_request_propagates_inference_not_found() -> None:
    resolver = InteractionResolver(_MissingReader())
    request = EvaluateRequest.model_validate(
        {"inference_id": "missing", "metrics": ["faithfulness"]}
    )
    with pytest.raises(InferenceNotFoundError):
        await resolver.resolve(request)


async def test_inline_resolution_rejects_an_incomplete_request() -> None:
    # Defense in depth: even if request validation were bypassed, the resolver
    # refuses to build an interaction from a half-specified inline request.
    resolver = InteractionResolver(reader=None)
    malformed = EvaluateRequest.model_construct(
        inference_id=None,
        input_text="src",
        output_text=None,
        prompt=None,
        metrics=["faithfulness"],
        metadata=EvaluationMetadata(),
    )
    with pytest.raises(ValueError, match="inline evaluation requires"):
        await resolver.resolve(malformed)
