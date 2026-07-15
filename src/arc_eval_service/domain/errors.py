"""Domain errors.

The prompt library, model registry and judge engine raise these instead of
importing FastAPI. They are captured per-metric by the judge engine and surfaced
as errored results, so a single metric failure never fails the whole request.
"""

from __future__ import annotations

from collections.abc import Iterable


class UnknownMetricError(ValueError):
    """Raised when a request references one or more metrics that are not defined."""

    def __init__(self, name: str | Iterable[str]) -> None:
        names = (name,) if isinstance(name, str) else tuple(name)
        self.names = names
        self.name = names[0] if names else ""
        if len(names) == 1:
            message = f"unknown metric '{self.name}'"
        else:
            joined = ", ".join(f"'{item}'" for item in names)
            message = f"unknown metrics: {joined}"
        super().__init__(message)


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


class ExperimentNotFoundError(Exception):
    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        super().__init__(f"experiment not found: {experiment_id}")


class ExperimentNameConflictError(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"experiment name already exists: {name}")


class EmptyDatasetError(Exception):
    """Raised when an experiment run is requested but the dataset is empty (409).

    A run must have something to score, so an empty dataset fails closed rather than
    producing an empty, meaningless run.
    """

    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        super().__init__(f"experiment has an empty dataset: {experiment_id}")
