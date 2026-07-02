"""What a judge is: prompt scaffolding and sampling settings for a model.

A judge is the *who grades* half of a judgement: an optional persona (system
prompt) layered before the metric rubric, sampling settings, and the model profile
to call. Instances live as one YAML file each next to this module; the loader
validates them into :class:`JudgeDefinition` once at startup.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
