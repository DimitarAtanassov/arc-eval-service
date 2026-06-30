"""initial schema: traces, spans, cases, eval_results

The service owns four tables: ``traces`` and ``spans`` capture the OTel
telemetry tree, ``cases`` holds eval-ready interactions, and ``eval_results``
holds one row per metric verdict (results cascade-delete with their case). There
is no aggregate table.

Revision ID: 0001
Revises:
Create Date: 2026-06-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=True),
        sa.Column("start_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("end_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("trace_id"),
    )
    op.create_index("ix_traces_request_id", "traces", ["request_id"])
    op.create_index("ix_traces_ingested_at", "traces", ["ingested_at"])

    op.create_table(
        "spans",
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("parent_span_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("start_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("end_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("span_id"),
    )
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_service_name", "spans", ["service_name"])
    op.create_index("ix_spans_ingested_at", "spans", ["ingested_at"])

    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index("ix_cases_request_id", "cases", ["request_id"])
    op.create_index("ix_cases_trace_id", "cases", ["trace_id"])
    op.create_index("ix_cases_created_at", "cases", ["created_at"])

    op.create_table(
        "eval_results",
        sa.Column("result_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("result_id"),
    )
    op.create_index("ix_eval_results_case_id", "eval_results", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_case_id", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index("ix_cases_created_at", table_name="cases")
    op.drop_index("ix_cases_trace_id", table_name="cases")
    op.drop_index("ix_cases_request_id", table_name="cases")
    op.drop_table("cases")

    op.drop_index("ix_spans_ingested_at", table_name="spans")
    op.drop_index("ix_spans_service_name", table_name="spans")
    op.drop_index("ix_spans_trace_id", table_name="spans")
    op.drop_table("spans")

    op.drop_index("ix_traces_ingested_at", table_name="traces")
    op.drop_index("ix_traces_request_id", table_name="traces")
    op.drop_table("traces")
