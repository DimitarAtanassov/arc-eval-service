"""Ingestion DTOs and domain models for the single eval-input endpoint.

The request carries one LLM interaction: the rendered prompt, the system message,
the model response and the model config. The domain models (:class:`NewEvalInput`,
:class:`EvalInput`) are what the service and repositories pass around; the row
mappers live with the repository.

``model_response`` and ``model_config`` are the wire and column names. Pydantic
reserves the ``model_config`` attribute for its own settings, so both payloads are
carried on the plainly named attributes ``response`` and ``config`` and exposed
under the ``model_*`` names via field aliases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvalInputRequest(BaseModel):
    """One LLM interaction to store for later evaluation."""

    rendered_prompt: str = Field(
        ..., min_length=1, description="The fully rendered prompt (the model input)."
    )
    system_message: str | None = Field(
        default=None, description="The system message, if any."
    )
    response: dict[str, Any] = Field(
        ..., alias="model_response", description="The model response payload."
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        alias="model_config",
        description="The model config used for the call.",
    )


class EvalInputResponse(BaseModel):
    """Identifier for the stored interaction."""

    eval_input_id: str


class NewEvalInput(BaseModel):
    """An eval input to persist. ``created_at`` is stamped by the database."""

    id: str
    rendered_prompt: str
    system_message: str | None
    response: dict[str, Any]
    config: dict[str, Any]


class EvalInput(NewEvalInput):
    """A persisted eval input, with its storage timestamp."""

    created_at: datetime
