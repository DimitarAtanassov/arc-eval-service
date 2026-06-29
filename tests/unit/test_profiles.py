"""Unit tests for model profiles + registry (BYOK resolution)."""

import pytest

from arc_eval_service.core.errors import ModelError, UnknownModelError
from arc_eval_service.models.anthropic import AnthropicModel
from arc_eval_service.models.openai_compat import OpenAICompatibleModel
from arc_eval_service.models.profiles import ModelProfile, ModelRegistry

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
    assert isinstance(model, OpenAICompatibleModel)
    assert model.name == "llama3"


def test_model_override_swaps_model_id() -> None:
    model = _registry().resolve("local", model_override="mistral")
    assert model.name == "mistral"


def test_unknown_profile_raises() -> None:
    with pytest.raises(UnknownModelError):
        _registry().resolve("nope")


def test_missing_api_key_env_raises_model_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_ANTHROPIC_KEY", raising=False)
    with pytest.raises(ModelError):
        _registry().resolve("claude")


def test_list_profiles_exposes_no_secrets() -> None:
    infos = {p.name: p for p in _registry().list_profiles()}
    assert infos["claude"].provider == "anthropic"
    # ModelProfileInfo has no api key field at all.
    assert not hasattr(infos["claude"], "api_key_env")


def test_has_respects_default() -> None:
    registry = _registry()
    assert registry.has(None) is True  # default exists
    assert registry.has("claude") is True
    assert registry.has("ghost") is False
