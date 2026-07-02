"""initial schema: eval_requests, evaluation_results

The service owns two tables. ``eval_requests`` holds one interaction submitted for
evaluation; ``evaluation_results`` holds one metric score per row against that
interaction (results cascade-delete with their request).

Revision ID: 0001
Revises:
Create Date: 2026-07-01

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
        "eval_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("inference_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("request_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_requests_inference_id", "eval_requests", ["inference_id"]
    )
    op.create_index("ix_eval_requests_created_at", "eval_requests", ["created_at"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("eval_request_id", sa.String(), nullable=False),
        sa.Column("inference_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("evaluator_name", sa.String(), nullable=False),
        sa.Column("evaluator_version", sa.String(), nullable=True),
        sa.Column("judge", postgresql.JSONB(), nullable=True),
        sa.Column("prompt", postgresql.JSONB(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["eval_request_id"], ["eval_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_results_eval_request_id",
        "evaluation_results",
        ["eval_request_id"],
    )
    op.create_index(
        "ix_evaluation_results_inference_id", "evaluation_results", ["inference_id"]
    )
    op.create_index(
        "ix_evaluation_results_metric_name", "evaluation_results", ["metric_name"]
    )
    op.create_index(
        "ix_evaluation_results_created_at", "evaluation_results", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_results_created_at", table_name="evaluation_results"
    )
    op.drop_index(
        "ix_evaluation_results_metric_name", table_name="evaluation_results"
    )
    op.drop_index(
        "ix_evaluation_results_inference_id", table_name="evaluation_results"
    )
    op.drop_index(
        "ix_evaluation_results_eval_request_id", table_name="evaluation_results"
    )
    op.drop_table("evaluation_results")

    op.drop_index("ix_eval_requests_created_at", table_name="eval_requests")
    op.drop_index("ix_eval_requests_inference_id", table_name="eval_requests")
    op.drop_table("eval_requests")
