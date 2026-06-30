"""ORM models: the four tables this service owns.

``traces`` and ``spans`` capture the OTel telemetry tree; ``cases`` holds the
eval-ready interactions; ``eval_results`` holds one row per metric verdict.
Results cascade-delete with their case. There is no aggregate table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class TraceRow(Base):
    """Header for one trace: identity, timing and originating request/service."""

    __tablename__ = "traces"

    trace_id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    service_name: Mapped[str | None] = mapped_column(String, nullable=True)
    start_unix_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_unix_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class SpanRow(Base):
    """One normalised OTel span, keyed on ``span_id`` for idempotent upserts."""

    __tablename__ = "spans"

    span_id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    service_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    start_unix_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_unix_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attributes: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class CaseRow(Base):
    """An eval-ready interaction; optionally linked to its originating trace."""

    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_metadata: Mapped[dict[str, str]] = mapped_column(
        "metadata", JSONB, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class ResultRow(Base):
    """One metric's verdict for a case (no aggregate, one row per metric)."""

    __tablename__ = "eval_results"

    result_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
