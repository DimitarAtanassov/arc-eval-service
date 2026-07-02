"""Unit tests for judge-model provider adapters (HTTP mocked with respx)."""

import json

import httpx
import pytest
import respx

from arc_eval_service.domain.errors import ModelError
from arc_eval_service.judging.ports import ModelSettings
from arc_eval_service.judging.providers.openai_compat import OpenAICompatibleModel
from arc_eval_service.judging.verdict import Verdict

pytestmark = pytest.mark.unit


@respx.mock
async def test_openai_compatible_honors_base_url() -> None:
    route = respx.post("http://localhost:1234/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "llama3",
                "choices": [{"message": {"content": '{"score": 0.5}'}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )
    )
    model = OpenAICompatibleModel(model="llama3", base_url="http://localhost:1234/v1")
    out = await model.complete(system=None, prompt="hi", settings=ModelSettings())
    assert route.called
    assert out.text == '{"score": 0.5}'
    assert out.output_tokens == 3
    # No structured-output request unless a schema is passed.
    assert "response_format" not in json.loads(route.calls.last.request.content)


@respx.mock
async def test_openai_compatible_requests_structured_output() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o",
                "choices": [{"message": {"content": '{"score": 1}'}}],
            },
        )
    )
    model = OpenAICompatibleModel(model="gpt-4o", api_key="sk")
    await model.complete(
        system=None, prompt="hi", settings=ModelSettings(), response_schema=Verdict
    )
    fmt = json.loads(route.calls.last.request.content)["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "verdict"
    assert "score" in fmt["json_schema"]["schema"]["properties"]


@respx.mock
async def test_openai_compatible_prepends_system_message() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o",
                "choices": [{"message": {"content": '{"score": 1}'}}],
            },
        )
    )
    model = OpenAICompatibleModel(model="gpt-4o", api_key="sk")
    await model.complete(
        system="You are a judge.", prompt="hi", settings=ModelSettings()
    )
    messages = json.loads(route.calls.last.request.content)["messages"]
    assert messages == [
        {"role": "system", "content": "You are a judge."},
        {"role": "user", "content": "hi"},
    ]


@respx.mock
async def test_adapter_wraps_http_error_as_model_error() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    model = OpenAICompatibleModel(model="gpt-4o", api_key="sk")
    with pytest.raises(ModelError):
        await model.complete(system=None, prompt="hi", settings=ModelSettings())
