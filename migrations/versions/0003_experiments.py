"""experiments and experiment_runs

Adds the experiment tables the eval service owns after experimentation moved out
of arc-model-lab. An experiment is a named (model, generation config) pair; an
experiment_run links one inference (and, when scored, the eval request that
produced its metrics) back to its experiment. experiment_runs.eval_request_id is
the precise join used to aggregate an experiment's scores without double-counting
re-evaluations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("generation_config", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_experiments_name"),
    )
    op.create_index("ix_experiments_created_at", "experiments", ["created_at"])

    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("experiment_id", sa.String(), nullable=False),
        sa.Column("inference_id", sa.String(), nullable=False),
        sa.Column("eval_request_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["eval_request_id"], ["eval_requests.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("inference_id", name="uq_experiment_runs_inference_id"),
    )
    op.create_index(
        "ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"]
    )
    op.create_index(
        "ix_experiment_runs_created_at", "experiment_runs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_runs_created_at", table_name="experiment_runs")
    op.drop_index("ix_experiment_runs_experiment_id", table_name="experiment_runs")
    op.drop_table("experiment_runs")
    op.drop_index("ix_experiments_created_at", table_name="experiments")
    op.drop_table("experiments")
