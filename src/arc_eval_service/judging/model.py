"""Judge-model port (dependency-inversion boundary).

Ports & adapters (hexagonal): the engine depends only on this protocol, never on
a concrete vendor SDK. A prompt is rendered to a single ``(system, prompt)`` pair
and handed to whichever model the request selected. Add a vendor or a self-hosted
endpoint by adding an adapter under :mod:`providers`; nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ModelSettings:
    """Inference knobs for a judge call. Judges run near-deterministically."""

    temperature: float = 0.0
    max_tokens: int = 1024


@dataclass(frozen=True, slots=True)
class ModelCompletion:
    """A model's raw text response plus identity and usage."""

    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class JudgeModel(Protocol):
    """The contract every judge-model adapter must satisfy."""

    name: str
    provider: str

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        """Run a single-turn completion and return the model's text."""
        ...
