"""ORM models: the two tables this service owns.

``eval_requests`` holds one interaction submitted for evaluation (the task type,
the input and output text, the rendered prompt, and the caller's correlation ids
from ``metadata``). ``evaluation_results`` holds one metric score per row against
that interaction (score, pass/fail, the judge's reasoning, and which evaluator
and judge model produced it).

Both tables are written on every ``POST /v1/evaluate`` call: one ``eval_requests``
row plus one ``evaluation_results`` row per metric scored. Storing one metric per
row (not a JSON blob) keeps the primary query paths -- score by metric, by model,
over time -- indexable in plain SQL.
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


class EvalRequestRow(Base):
    """One interaction submitted for evaluation."""

    __tablename__ = "eval_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Caller correlation ids, lifted out of ``metadata`` for indexed lookups.
    inference_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # ``metadata`` is reserved on the declarative base, so the attribute (and
    # column) is named ``request_metadata``.
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class EvaluationResultRow(Base):
    """One metric score against one evaluation request."""

    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    eval_request_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("eval_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ``inference_id`` and ``model_id`` are denormalised from the request so the
    # common observability queries (score per metric, per model) need no join.
    inference_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metric_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluator_name: Mapped[str] = mapped_column(String, nullable=False)
    evaluator_version: Mapped[str | None] = mapped_column(String, nullable=True)
    # The judge model, its settings, and the system prompt that produced the score
    # (the model under test is ``model_id``).
    judge: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # The metric prompt template and the input variables it was rendered with.
    prompt: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
