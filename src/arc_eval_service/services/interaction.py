"""The complete interaction the scoring core operates on.

A completed interaction to score: the input, the output, the metrics to score it
against, and an optional system prompt. Both ``POST /v1/evaluate`` and an experiment
run build this value object, so the scoring service depends on it rather than on any
request or dataset shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Interaction:
    """A completed interaction to score."""

    input_text: str
    output_text: str
    metrics: tuple[str, ...]
    system_text: str | None = None
