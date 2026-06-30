"""ORM models: the four tables this service owns.

``prompt_templates`` stores a template once per distinct content; ``eval_inputs``
holds one LLM interaction to evaluate (the rendered prompt, the context that
rendered it, the response and the model config); ``metrics`` holds a metric
definition; ``evaluation_runs`` holds one metric run against one input with the
judge config used and the result.

The ingestion endpoint writes ``prompt_templates`` and ``eval_inputs`` only;
``metrics`` and ``evaluation_runs`` are written by the evaluation logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from arc_eval_service.db.base import Base


class PromptTemplateRow(Base):
    """A prompt template with placeholders, deduplicated on its content hash."""

    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvalInputRow(Base):
    """One LLM interaction to evaluate, rendered from a prompt template."""

    __tablename__ = "eval_inputs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    prompt_template_id: Mapped[str] = mapped_column(
        String, ForeignKey("prompt_templates.id"), nullable=False, index=True
    )
    template_context: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    rendered_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    system_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    llm_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class MetricRow(Base):
    """A metric definition: a name plus an optional inline prompt or template ref."""

    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("prompt_templates.id"), nullable=True, index=True
    )
    input_variables: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvaluationRunRow(Base):
    """One metric run against one input: the judge config used and the result."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    eval_input_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("eval_inputs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_id: Mapped[str] = mapped_column(
        String, ForeignKey("metrics.id"), nullable=False, index=True
    )
    judge_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
