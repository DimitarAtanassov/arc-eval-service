"""Evaluator registry (registry pattern, no plugin framework).

The registry maps a stable string key to a stateless evaluator instance. New
evaluators become available by registering them in :func:`default_registry`;
nothing else in the service needs to change.
"""

from __future__ import annotations

from arc_eval_service.core.errors import UnknownEvaluatorError
from arc_eval_service.evaluators.base import Evaluator
from arc_eval_service.evaluators.cost import CostEvaluator
from arc_eval_service.evaluators.exact_match import ExactMatchEvaluator
from arc_eval_service.evaluators.heuristic import HeuristicEvaluator
from arc_eval_service.evaluators.latency import LatencyEvaluator
from arc_eval_service.evaluators.regex import RegexEvaluator
from arc_eval_service.evaluators.token import TokenEvaluator


class EvaluatorRegistry:
    """In-process registry of evaluator strategies keyed by name."""

    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {}

    def register(self, evaluator: Evaluator) -> None:
        """Register ``evaluator`` under its ``name`` (rejecting duplicates)."""
        if evaluator.name in self._evaluators:
            msg = f"evaluator '{evaluator.name}' already registered"
            raise ValueError(msg)
        self._evaluators[evaluator.name] = evaluator

    def has(self, name: str) -> bool:
        """Return whether an evaluator is registered under ``name``."""
        return name in self._evaluators

    def get(self, name: str) -> Evaluator:
        """Return the evaluator for ``name`` or raise :class:`UnknownEvaluatorError`."""
        try:
            return self._evaluators[name]
        except KeyError as exc:
            raise UnknownEvaluatorError(name) from exc

    def available(self) -> list[Evaluator]:
        """Return all registered evaluators, ordered by name."""
        return [self._evaluators[name] for name in sorted(self._evaluators)]


def default_registry() -> EvaluatorRegistry:
    """Build the registry with all MVP evaluators registered."""
    registry = EvaluatorRegistry()
    for evaluator in (
        ExactMatchEvaluator(),
        RegexEvaluator(),
        HeuristicEvaluator(),
        LatencyEvaluator(),
        TokenEvaluator(),
        CostEvaluator(),
    ):
        registry.register(evaluator)
    return registry
