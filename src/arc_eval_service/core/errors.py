"""Domain errors.

Services and judges raise these instead of importing FastAPI; the api/ layer
maps them to HTTP responses. This keeps HTTP concerns out of the lower layers.
"""

from __future__ import annotations


class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} '{identifier}' not found")


class UnknownJudgeError(ValueError):
    """Raised when a request references a judge that is not registered."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown judge '{name}'")


class UnknownModelError(ValueError):
    """Raised when a request references a model profile that is not configured."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown model profile '{name}'")


class EvaluationError(Exception):
    """Raised by a judge when it cannot score the given input.

    These are *expected* failures (missing required case fields, malformed
    config, an unparseable model verdict) and are captured per-judge rather than
    failing the whole request.
    """


class ModelError(Exception):
    """Raised when a judge model call fails (transport, auth, bad response).

    Captured per-judge by the orchestrator and surfaced as an errored result;
    it never fails the whole evaluation request.
    """
