"""Unit tests for model profiles + registry (BYOK resolution)."""

import pytest

from arc_eval_service.core.errors import ModelError, UnknownModelError
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry
from arc_eval_service.judging.providers.anthropic import AnthropicModel
from arc_eval_service.judging.providers.openai_compat import OpenAICompatibleModel

pytestmark = pytest.mark.unit


def _registry() -> ModelRegistry:
    return ModelRegistry(
        [
            ModelProfile(
                name="claude",
                provider="anthropic",
                model="claude-opus-4-8",
                api_key_env="TEST_ANTHROPIC_KEY",
            ),
            ModelProfile(
                name="local",
                provider="openai_compatible",
                model="llama3",
                base_url="http://localhost:1234/v1",
            ),
        ],
        default="local",
    )


def test_resolves_provider_specific_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "sk-live")
    registry = _registry()
    assert isinstance(registry.resolve("claude"), AnthropicModel)
    assert isinstance(registry.resolve("local"), OpenAICompatibleModel)


def test_default_profile_used_when_unspecified() -> None:
    model = _registry().resolve(None)
    assert isinstance(model, OpenAICompatibleModel) and model.name == "llama3"


def test_model_override_swaps_model_id() -> None:
    assert _registry().resolve("local", model_override="mistral").name == "mistral"


def test_unknown_profile_raises() -> None:
    with pytest.raises(UnknownModelError):
        _registry().resolve("nope")


def test_missing_api_key_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_ANTHROPIC_KEY", raising=False)
    with pytest.raises(ModelError):
        _registry().resolve("claude")


def test_profiles_lists_all_configured() -> None:
    assert {p.name for p in _registry().profiles()} == {"claude", "local"}


def test_has_respects_default() -> None:
    registry = _registry()
    assert registry.has(None) and registry.has("claude")
    assert not registry.has("ghost")
