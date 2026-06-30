"""Metric registry (registry pattern, no plugin framework).

Maps a stable string key to a stateless metric. A new metric becomes available by
registering it in :func:`default_registry`; nothing else changes.
"""

from __future__ import annotations

from arc_eval_service.core.errors import UnknownMetricError
from arc_eval_service.metrics.base import Metric
from arc_eval_service.metrics.builtins.answer_relevance import AnswerRelevanceMetric
from arc_eval_service.metrics.builtins.custom import CustomMetric
from arc_eval_service.metrics.builtins.faithfulness import FaithfulnessMetric
from arc_eval_service.metrics.builtins.safety import SafetyMetric


class MetricRegistry:
    """In-process registry of metrics keyed by name."""

    def __init__(self) -> None:
        self._metrics: dict[str, Metric] = {}

    def register(self, metric: Metric) -> None:
        """Register ``metric`` under its ``name`` (rejecting duplicates)."""
        if metric.name in self._metrics:
            raise ValueError(f"metric '{metric.name}' already registered")
        self._metrics[metric.name] = metric

    def has(self, name: str) -> bool:
        """Return whether a metric is registered under ``name``."""
        return name in self._metrics

    def get(self, name: str) -> Metric:
        """Return the metric for ``name`` or raise :class:`UnknownMetricError`."""
        try:
            return self._metrics[name]
        except KeyError as exc:
            raise UnknownMetricError(name) from exc

    def available(self) -> list[Metric]:
        """Return all registered metrics, ordered by name."""
        return [self._metrics[name] for name in sorted(self._metrics)]


def default_registry() -> MetricRegistry:
    """Build the registry with all built-in metrics registered."""
    registry = MetricRegistry()
    for metric in (
        FaithfulnessMetric(),
        AnswerRelevanceMetric(),
        SafetyMetric(),
        CustomMetric(),
    ):
        registry.register(metric)
    return registry
