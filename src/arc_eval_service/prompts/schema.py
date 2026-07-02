"""Declarative schema for the prompt library (metrics and judges).

Loaded from per-file YAML (one file per metric and judge) and validated once at
startup, then treated as immutable. A **metric** is a scoring criterion (a rubric,
which case fields it needs, a case-layout template, and a pass threshold). A
**judge** is the prompt scaffolding and sampling settings for a model (an optional
system prompt plus the model profile to call). The engine composes the two at
score time.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from arc_eval_service.core.errors import UnknownJudgeError, UnknownMetricError


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


class JudgeDefinition(BaseModel):
    """Prompt scaffolding and sampling settings for a judge model."""

    model_config = ConfigDict(frozen=True)

    version: str = "v1"
    system_prompt: str | None = Field(
        default=None,
        description="Optional persona, prepended before the metric rubric.",
    )
    temperature: float = Field(default=0.0, ge=0.0)
    max_tokens: int = Field(default=1024, gt=0)
    model_profile: str | None = Field(
        default=None,
        description="Model profile to call; the default profile when omitted.",
    )


class PromptLibrary(BaseModel):
    """The metric and judge definitions, keyed by name."""

    metrics: dict[str, MetricDefinition]
    judges: dict[str, JudgeDefinition]

    def metric(self, name: str) -> MetricDefinition:
        """Return the metric definition, or raise :class:`UnknownMetricError`."""
        try:
            return self.metrics[name]
        except KeyError as exc:
            raise UnknownMetricError(name) from exc

    def judge(self, name: str) -> JudgeDefinition:
        """Return the judge definition, or raise :class:`UnknownJudgeError`."""
        try:
            return self.judges[name]
        except KeyError as exc:
            raise UnknownJudgeError(name) from exc
