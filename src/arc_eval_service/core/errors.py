"""Domain errors.

Services and evaluators raise these instead of importing FastAPI; the api/ layer
maps them to HTTP responses. This keeps HTTP concerns out of the lower layers.
"""

from __future__ import annotations


class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} '{identifier}' not found")


class UnknownEvaluatorError(ValueError):
    """Raised when a request references an evaluator that is not registered."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown evaluator '{name}'")


class EvaluationError(Exception):
    """Raised by an evaluator when it cannot score the given input.

    These are *expected* failures (missing reference text, malformed config,
    absent metrics) and are captured per-evaluator rather than failing the whole
    request.
    """
