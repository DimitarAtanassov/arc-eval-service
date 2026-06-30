"""Ingestion DTOs and domain models for the single eval-input endpoint.

The request carries one LLM interaction: the prompt template, the context that
rendered it (placeholder to value), the rendered prompt, the system message, the
response and the model config. The domain models (:class:`NewEvalInput`,
:class:`EvalInput`) are what the service and repositories pass around; the row
mappers live with the repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvalInputRequest(BaseModel):
    """One LLM interaction to store for later evaluation."""

    prompt_template: str = Field(
        ..., min_length=1, description="The prompt template, with placeholders."
    )
    template_context: dict[str, str] = Field(
        default_factory=dict,
        description="Placeholder name to the value substituted into the template.",
    )
    rendered_prompt: str = Field(
        ..., min_length=1, description="The fully rendered prompt (the LLM input)."
    )
    system_message: str | None = Field(
        default=None, description="The system message, if any."
    )
    llm_response: dict[str, Any] = Field(..., description="The LLM response payload.")
    llm_config: dict[str, Any] = Field(
        default_factory=dict, description="The LLM config used for the call."
    )


class EvalInputResponse(BaseModel):
    """Identifiers for the stored interaction."""

    eval_input_id: str
    prompt_template_id: str


class NewEvalInput(BaseModel):
    """An eval input to persist. ``created_at`` is stamped by the database."""

    id: str
    prompt_template_id: str
    template_context: dict[str, str]
    rendered_prompt: str
    system_message: str | None
    llm_response: dict[str, Any]
    llm_config: dict[str, Any]


class EvalInput(NewEvalInput):
    """A persisted eval input, with its storage timestamp."""

    created_at: datetime
