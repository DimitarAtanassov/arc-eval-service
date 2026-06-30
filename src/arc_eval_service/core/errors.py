"""Domain errors.

Services and the judge engine raise these instead of importing FastAPI; the app
layer maps them to HTTP responses, keeping HTTP concerns out of the lower layers.
"""

from __future__ import annotations


class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} '{identifier}' not found")


class UnknownMetricError(ValueError):
    """Raised when a request references a metric that is not registered."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown metric '{name}'")


class UnknownModelError(ValueError):
    """Raised when a request references a model profile that is not configured."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown model profile '{name}'")


class EvaluationError(Exception):
    """Raised when a metric cannot score the given input.

    Expected failures (missing required case fields, malformed config, an
    unparseable model verdict), captured per-metric rather than failing the
    whole request.
    """


class ModelError(Exception):
    """Raised when a judge model call fails (transport, auth, bad response).

    Captured per-metric and surfaced as an errored result; never fails the whole
    evaluation request.
    """
