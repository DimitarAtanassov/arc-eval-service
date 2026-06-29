"""Unit tests for the judge-model adapters (real wire shape, mocked transport)."""

import httpx
import pytest
import respx

from arc_eval_service.core.errors import ModelError
from arc_eval_service.models.anthropic import AnthropicModel
from arc_eval_service.models.base import ModelSettings
from arc_eval_service.models.openai_compat import OpenAICompatibleModel

pytestmark = pytest.mark.unit


@respx.mock
async def test_anthropic_adapter_parses_text() -> None:
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": '{"score": 0.9}'}],
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        )
    )
    model = AnthropicModel(model="claude-opus-4-8", api_key="sk-test")
    out = await model.complete(system="sys", prompt="hi", settings=ModelSettings())
    assert out.text == '{"score": 0.9}'
    assert out.model == "claude-opus-4-8"
    assert out.input_tokens == 10


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


@respx.mock
async def test_adapter_wraps_http_error_as_model_error() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    model = OpenAICompatibleModel(model="gpt-4o", api_key="sk")
    with pytest.raises(ModelError):
        await model.complete(system=None, prompt="hi", settings=ModelSettings())
