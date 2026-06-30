"""Metric contract: a scoring criterion, independent of the judging mechanism.

A metric declares *what* it grades (``instructions``), *how* the case is laid out
for grading (``render``), which case fields it ``requires`` and its pass
``threshold``. It knows nothing about models, prompting envelopes or parsing:
the judge engine supplies those. This keeps metrics and judging orthogonal --
add a metric without touching the engine, swap the engine without touching
metrics.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from arc_eval_service.evaluation.schemas import ConfigValue, EvaluationCase


@runtime_checkable
class Metric(Protocol):
    """A pure scoring criterion."""

    name: str
    description: str
    requires: tuple[str, ...]
    threshold: float

    def instructions(self, config: Mapping[str, ConfigValue]) -> str:
        """Return the rubric: what this metric grades and how."""
        ...

    def render(self, case: EvaluationCase) -> str:
        """Return the case laid out for the model to grade."""
        ...
