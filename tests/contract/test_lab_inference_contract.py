from __future__ import annotations

import json

import httpx
import pytest

from arc_eval_service.clients.lab_inference_client import (
    InferenceResult,
    InferenceRunRequest,
    LabInferenceClient,
    LabInferenceSettings,
    build_lab_inference_client,
)
from arc_eval_service.domain.errors import (
    InferenceNotFoundError,
    LabInferenceError,
    LabRequestInvalidError,
    ModelInactiveError,
    ModelNotFoundError,
)
from arc_eval_service.domain.experiment import GenerationConfig

pytestmark = pytest.mark.contract

_RESPONSE = {
    "id": "inf-1",
    "model_id": "mdl-1",
    "input_text": "source",
    "prompt": "Summarize:",
    "output_text": "summary",
    "latency_ms": 12,
    "prompt_tokens": 5,
    "completion_tokens": 3,
    "created_at": "2026-07-08T00:00:00Z",
}


def _request() -> InferenceRunRequest:
    return InferenceRunRequest(
        model_name="candidate",
        input_text="source",
        generation_config=GenerationConfig(temperature=0.0, max_output_tokens=64),
    )


def _client(handler: httpx.MockTransport | object) -> LabInferenceClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return LabInferenceClient(
        httpx.AsyncClient(base_url="http://lab", transport=transport)
    )


async def test_run_posts_contract_and_parses_response() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["cid"] = request.headers.get("X-Correlation-ID")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_RESPONSE)

    client = _client(handler)
    result = await client.run(_request(), correlation_id="cid-1")
    await client.aclose()

    assert seen["url"] == "http://lab/v1/inference:run"
    assert seen["cid"] == "cid-1"
    assert seen["body"] == {
        "model_name": "candidate",
        "input_text": "source",
        "generation_config": {"temperature": 0.0, "max_output_tokens": 64},
        "allow_inactive": True,
        "prompt_template": None,
        "variables": {},
    }
    assert isinstance(result, InferenceResult)
    assert result.id == "inf-1"
    assert result.output_text == "summary"


async def test_not_found_maps_to_model_not_found() -> None:
    client = _client(lambda _: httpx.Response(404, json={"detail": "unknown model"}))
    with pytest.raises(ModelNotFoundError):
        await client.run(_request())


async def test_unprocessable_maps_to_lab_request_invalid() -> None:
    body = {"detail": "Missing variables for template 'translate': ['target_language']"}
    client = _client(lambda _: httpx.Response(422, json=body))
    with pytest.raises(LabRequestInvalidError, match="target_language"):
        await client.run(_request())


async def test_unprocessable_with_non_json_body_still_raises_invalid() -> None:
    client = _client(lambda _: httpx.Response(422, content=b"not json"))
    with pytest.raises(LabRequestInvalidError):
        await client.run(_request())


async def test_unprocessable_with_non_object_json_still_raises_invalid() -> None:
    client = _client(lambda _: httpx.Response(422, json=["nope"]))
    with pytest.raises(LabRequestInvalidError):
        await client.run(_request())


async def test_unprocessable_with_non_string_detail_still_raises_invalid() -> None:
    client = _client(lambda _: httpx.Response(422, json={"detail": {"nested": "x"}}))
    with pytest.raises(LabRequestInvalidError):
        await client.run(_request())


async def test_run_serializes_prompt_template_and_variables() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_RESPONSE)

    request = InferenceRunRequest(
        model_name="candidate",
        input_text="source",
        generation_config=GenerationConfig(temperature=0.0, max_output_tokens=64),
        prompt_template="translate",
        variables={"target_language": "French"},
    )
    await _client(handler).run(request)

    assert seen["body"] == {
        "model_name": "candidate",
        "input_text": "source",
        "generation_config": {"temperature": 0.0, "max_output_tokens": 64},
        "allow_inactive": True,
        "prompt_template": "translate",
        "variables": {"target_language": "French"},
    }


async def test_conflict_maps_to_model_inactive() -> None:
    client = _client(lambda _: httpx.Response(409, json={"detail": "inactive"}))
    with pytest.raises(ModelInactiveError):
        await client.run(_request())


async def test_server_error_maps_to_lab_inference_error() -> None:
    client = _client(lambda _: httpx.Response(500, text="boom"))
    with pytest.raises(LabInferenceError):
        await client.run(_request())


async def test_connect_error_maps_to_lab_inference_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client = _client(handler)
    with pytest.raises(LabInferenceError):
        await client.run(_request())


async def test_transport_error_maps_to_lab_inference_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler)
    with pytest.raises(LabInferenceError):
        await client.run(_request())


async def test_non_json_maps_to_lab_inference_error() -> None:
    client = _client(lambda _: httpx.Response(200, content=b"not json"))
    with pytest.raises(LabInferenceError):
        await client.run(_request())


async def test_bad_schema_maps_to_lab_inference_error() -> None:
    client = _client(lambda _: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(LabInferenceError):
        await client.run(_request())


async def test_get_inference_fetches_and_parses() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["cid"] = request.headers.get("X-Correlation-ID")
        return httpx.Response(200, json=_RESPONSE)

    client = _client(handler)
    result = await client.get_inference("inf-1", correlation_id="cid-2")
    await client.aclose()

    assert seen["url"] == "http://lab/inference/inf-1"
    assert seen["cid"] == "cid-2"
    assert isinstance(result, InferenceResult)
    assert result.output_text == "summary"


async def test_get_inference_not_found_maps_to_inference_not_found() -> None:
    client = _client(lambda _: httpx.Response(404, json={"detail": "unknown"}))
    with pytest.raises(InferenceNotFoundError):
        await client.get_inference("missing")


async def test_get_inference_unprocessable_maps_to_lab_request_invalid() -> None:
    client = _client(lambda _: httpx.Response(422, json={"detail": "badly formed id"}))
    with pytest.raises(LabRequestInvalidError):
        await client.get_inference("not-a-uuid")


async def test_get_inference_server_error_maps_to_lab_inference_error() -> None:
    client = _client(lambda _: httpx.Response(500, text="boom"))
    with pytest.raises(LabInferenceError):
        await client.get_inference("inf-1")


async def test_get_inference_connect_error_maps_to_lab_inference_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client = _client(handler)
    with pytest.raises(LabInferenceError):
        await client.get_inference("inf-1")


async def test_get_inference_transport_error_maps_to_lab_inference_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler)
    with pytest.raises(LabInferenceError):
        await client.get_inference("inf-1")


async def test_get_inference_non_json_maps_to_lab_inference_error() -> None:
    client = _client(lambda _: httpx.Response(200, content=b"not json"))
    with pytest.raises(LabInferenceError):
        await client.get_inference("inf-1")


async def test_get_inference_bad_schema_maps_to_lab_inference_error() -> None:
    client = _client(lambda _: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(LabInferenceError):
        await client.get_inference("inf-1")


def test_build_returns_none_without_url() -> None:
    assert build_lab_inference_client(LabInferenceSettings(service_url="")) is None


def test_build_returns_client_with_url() -> None:
    client = build_lab_inference_client(LabInferenceSettings(service_url="http://lab"))
    assert isinstance(client, LabInferenceClient)
