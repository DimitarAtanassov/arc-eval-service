"""Domain errors.

The prompt library, model registry and judge engine raise these instead of
importing FastAPI. They are captured per-metric by the judge engine and surfaced
as errored results, so a single metric failure never fails the whole request.
"""

from __future__ import annotations


class UnknownMetricError(ValueError):
    """Raised when a request references a metric that is not defined."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown metric '{name}'")


class UnknownJudgeError(ValueError):
    """Raised when a request references a judge that is not defined."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown judge '{name}'")


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
