"""Model profiles + registry (BYOK without secrets in payloads).

A **profile** is a named, server-side model configuration: which provider, which
model id, an optional ``base_url`` (self-hosted), and the **name of the env var**
that holds the API key. The secret itself is never stored in the profile, a
request body or a log -- only resolved at call time from the environment.

Requests select a profile by name and may override the concrete model id within
it. This keeps credentials an operator concern and model choice a caller concern.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from arc_eval_service.domain.errors import ModelError, UnknownModelError
from arc_eval_service.judging.ports import JudgeModel
from arc_eval_service.judging.providers.openai_compat import OpenAICompatibleModel

Provider = Literal["openai_compatible"]


class ModelProfile(BaseModel):
    """A named, server-side judge-model configuration (no secret stored)."""

    name: str = Field(..., min_length=1)
    provider: Provider
    model: str = Field(..., min_length=1)
    base_url: str | None = None
    api_key_env: str | None = Field(
        default=None, description="Env var name holding the API key (resolved at call)."
    )


class ModelRegistry:
    """Resolves profile names into ready-to-call :class:`JudgeModel` adapters."""

    def __init__(
        self, profiles: list[ModelProfile], *, default: str | None = None
    ) -> None:
        self._profiles = {profile.name: profile for profile in profiles}
        self._default = default or (profiles[0].name if profiles else None)

    def has(self, name: str | None) -> bool:
        """Whether ``name`` (or the default when ``None``) resolves to a profile."""
        resolved = name or self._default
        return resolved is not None and resolved in self._profiles

    def profiles(self) -> list[ModelProfile]:
        """Return the configured profiles (the discovery surface maps these)."""
        return list(self._profiles.values())

    def resolve(
        self, name: str | None = None, *, model_override: str | None = None
    ) -> JudgeModel:
        """Build the adapter for profile ``name`` (or the default).

        Raises:
            UnknownModelError: no such profile (and no default).
            ModelError: the profile's ``api_key_env`` is set but unset in the env.
        """
        profile_name = name or self._default
        if profile_name is None or profile_name not in self._profiles:
            raise UnknownModelError(profile_name or "<default>")
        profile = self._profiles[profile_name]

        api_key: str | None = None
        if profile.api_key_env:
            api_key = os.environ.get(profile.api_key_env)
            if not api_key:
                raise ModelError(
                    f"profile '{profile.name}' expects env '{profile.api_key_env}'"
                )

        model_id = model_override or profile.model
        return OpenAICompatibleModel(
            model=model_id,
            base_url=profile.base_url or "https://api.openai.com/v1",
            api_key=api_key,
        )
