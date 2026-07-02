"""Scoring policy: which metrics run for a given task type.

A small in-code table on purpose: this is scoring policy, not configuration, and
lives next to the code that applies it. An unknown task type falls back to
``DEFAULT_METRICS``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("arc_eval_service.services.policy")

# Which metrics run for a given task type.
TASK_METRICS: dict[str, tuple[str, ...]] = {
    "summarization": ("faithfulness", "answer_relevance"),
}
DEFAULT_METRICS: tuple[str, ...] = ("answer_relevance", "safety")


def metrics_for(task_type: str) -> tuple[str, ...]:
    """Return the metrics to score for ``task_type`` (falls back to defaults)."""
    metrics = TASK_METRICS.get(task_type)
    if metrics is None:
        logger.warning(
            "unknown task type; using default metrics",
            extra={"task_type": task_type, "metrics": DEFAULT_METRICS},
        )
        return DEFAULT_METRICS
    return metrics
