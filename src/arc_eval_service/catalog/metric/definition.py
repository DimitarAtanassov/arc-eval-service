"""What a metric is: a scoring criterion declared in YAML.

A metric is the *what to grade* half of a judgement: a rubric, the case fields it
needs, a case-layout template, and a pass threshold. Instances live as one YAML
file each next to this module; the loader validates them into
:class:`MetricDefinition` once at startup.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetricDefinition(BaseModel):
    """A scoring criterion: what to grade, which fields it needs, how to lay them out."""

    model_config = ConfigDict(frozen=True)

    version: str = "v1"
    rubric: str = Field(..., min_length=1, description="What this metric grades.")
    template: str = Field(
        ..., min_length=1, description="Case layout with {input}/{output}/... slots."
    )
    requires: tuple[str, ...] = ()
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
