"""Unit tests for model profiles + registry (BYOK resolution)."""

import pytest

from arc_eval_service.domain.errors import ModelError, UnknownModelError
from arc_eval_service.judging.profiles import ModelProfile, ModelRegistry
from arc_eval_service.judging.providers.openai_compat import OpenAICompatibleModel

pytestmark = pytest.mark.unit


def _registry() -> ModelRegistry:
    return ModelRegistry(
        [
            ModelProfile(
                name="hosted",
                provider="openai_compatible",
                model="gpt-4o",
                api_key_env="TEST_OPENAI_KEY",
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


def test_resolves_openai_compatible_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_OPENAI_KEY", "sk-live")
    registry = _registry()
    assert isinstance(registry.resolve("hosted"), OpenAICompatibleModel)
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
    monkeypatch.delenv("TEST_OPENAI_KEY", raising=False)
    with pytest.raises(ModelError):
        _registry().resolve("hosted")


def test_profiles_lists_all_configured() -> None:
    assert {p.name for p in _registry().profiles()} == {"hosted", "local"}


def test_has_respects_default() -> None:
    registry = _registry()
    assert registry.has(None) and registry.has("hosted")
    assert not registry.has("ghost")
