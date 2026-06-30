"""initial schema: prompt_templates, eval_inputs, metrics, evaluation_runs

The service owns four tables: ``prompt_templates`` stores a template once per
distinct content; ``eval_inputs`` holds one LLM interaction to evaluate;
``metrics`` holds a metric definition; ``evaluation_runs`` holds one metric run
against one input (runs cascade-delete with their input).

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
        "prompt_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash"),
    )

    op.create_table(
        "eval_inputs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("prompt_template_id", sa.String(), nullable=False),
        sa.Column("template_context", postgresql.JSONB(), nullable=False),
        sa.Column("rendered_prompt", sa.Text(), nullable=False),
        sa.Column("system_message", sa.Text(), nullable=True),
        sa.Column("llm_response", postgresql.JSONB(), nullable=False),
        sa.Column("llm_config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["prompt_template_id"], ["prompt_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_inputs_prompt_template_id", "eval_inputs", ["prompt_template_id"]
    )
    op.create_index("ix_eval_inputs_created_at", "eval_inputs", ["created_at"])

    op.create_table(
        "metrics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("prompt_template_id", sa.String(), nullable=True),
        sa.Column("input_variables", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["prompt_template_id"], ["prompt_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_metrics_prompt_template_id", "metrics", ["prompt_template_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("eval_input_id", sa.String(), nullable=False),
        sa.Column("metric_id", sa.String(), nullable=False),
        sa.Column("judge_config", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["eval_input_id"], ["eval_inputs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_eval_input_id", "evaluation_runs", ["eval_input_id"]
    )
    op.create_index("ix_evaluation_runs_metric_id", "evaluation_runs", ["metric_id"])
    op.create_index("ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_metric_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_eval_input_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_index("ix_metrics_prompt_template_id", table_name="metrics")
    op.drop_table("metrics")

    op.drop_index("ix_eval_inputs_created_at", table_name="eval_inputs")
    op.drop_index("ix_eval_inputs_prompt_template_id", table_name="eval_inputs")
    op.drop_table("eval_inputs")

    op.drop_table("prompt_templates")
