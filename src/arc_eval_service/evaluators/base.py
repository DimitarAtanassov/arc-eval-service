"""Evaluator strategy interface and shared config/scoring helpers.

Every evaluator is a stateless strategy implementing :class:`Evaluator`. The
orchestrator measures latency; evaluators only compute a score, a pass/fail flag
and human-readable details. Expected failures (missing inputs, bad config) are
signalled by raising :class:`~arc_eval_service.core.errors.EvaluationError`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.schemas.models import (
    ConfigValue,
    EvaluationResult,
    EvaluatorInput,
)


class Evaluator(ABC):
    """Abstract strategy: score one AI interaction.

    Subclasses set ``name`` (the registry key) and ``description`` and implement
    :meth:`evaluate`.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def evaluate(self, data: EvaluatorInput) -> EvaluationResult:
        """Score ``data`` and return an :class:`EvaluationResult`.

        Implementations must not set ``latency_ms``; the orchestrator overwrites
        it with the measured wall-clock duration.
        """
        raise NotImplementedError


# -- scoring helpers -------------------------------------------------------


def clamp01(value: float) -> float:
    """Clamp ``value`` into the inclusive ``[0.0, 1.0]`` range."""
    return max(0.0, min(1.0, value))


def ratio_score(limit: float, actual: float) -> float:
    """Graded score for "actual should not exceed limit" checks.

    Returns ``1.0`` when within budget and degrades towards ``0.0`` the further
    ``actual`` overshoots ``limit``.
    """
    if actual <= 0:
        return 1.0
    return clamp01(limit / actual)


# -- config helpers (no ``Any``; all values are scalar ConfigValue) --------


def require_str(config: Mapping[str, ConfigValue], key: str) -> str:
    """Return a required string config value or raise :class:`EvaluationError`."""
    if key not in config:
        raise EvaluationError(f"missing required config '{key}'")
    value = config[key]
    if not isinstance(value, str):
        raise EvaluationError(f"config '{key}' must be a string")
    return value


def require_number(config: Mapping[str, ConfigValue], key: str) -> float:
    """Return a required numeric config value or raise :class:`EvaluationError`."""
    if key not in config:
        raise EvaluationError(f"missing required config '{key}'")
    value = config[key]
    # ``bool`` is an ``int`` subclass; reject it so flags are not read as numbers.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"config '{key}' must be a number")
    return float(value)


def optional_bool(
    config: Mapping[str, ConfigValue], key: str, *, default: bool
) -> bool:
    """Return an optional boolean config value or ``default``."""
    if key not in config:
        return default
    value = config[key]
    if not isinstance(value, bool):
        raise EvaluationError(f"config '{key}' must be a boolean")
    return value


def optional_str(config: Mapping[str, ConfigValue], key: str, default: str) -> str:
    """Return an optional string config value or ``default``."""
    if key not in config:
        return default
    value = config[key]
    if not isinstance(value, str):
        raise EvaluationError(f"config '{key}' must be a string")
    return value


def optional_number(
    config: Mapping[str, ConfigValue], key: str, default: float | None
) -> float | None:
    """Return an optional numeric config value or ``default``."""
    if key not in config:
        return default
    value = config[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"config '{key}' must be a number")
    return float(value)
