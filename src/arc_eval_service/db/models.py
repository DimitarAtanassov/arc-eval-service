"""ORM models: the three tables this service owns.

``eval_inputs`` holds one LLM interaction to evaluate (the rendered prompt, the
system message, the model response and the model config); ``metrics`` holds a
metric definition (a unique name and an optional prompt); ``evaluation_runs``
holds one metric run against one input with the judge config used and the result.

The ingestion endpoint writes ``eval_inputs`` only; ``metrics`` and
``evaluation_runs`` are written by the evaluation logic.
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


class EvalInputRow(Base):
    """One LLM interaction to evaluate: the rendered prompt, response and config."""

    __tablename__ = "eval_inputs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    rendered_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    system_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class MetricRow(Base):
    """A metric definition: a unique name plus an optional inline prompt."""

    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
