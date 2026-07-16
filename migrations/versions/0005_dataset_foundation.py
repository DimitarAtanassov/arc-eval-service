"""dataset evaluator foundation: dataset entries and run items

Additive foundation for arc-eval-service becoming a dataset evaluator. Creates
``experiment_dataset_entries`` (one completed interaction per row) and
``experiment_run_items`` (links a dataset entry scored in a run to its eval
request), and adds ``experiments.metrics`` and ``experiment_runs.status``.

All additive: the two column adds are metadata-only (constant defaults, no table
rewrite in PostgreSQL 11+) and the new tables are empty, so nothing existing
breaks. The invasive reshape (dropping model_name, generation_config, and the old
run linkage) is a later migration.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-15

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail fast rather than queue behind a long-running query. The column adds are
    # metadata-only; the table creates take a brief lock.
    op.execute("SET lock_timeout = '4s'")
    op.execute("SET statement_timeout = '1min'")

    op.add_column(
        "experiments",
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "experiment_runs",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'completed'"),
        ),
    )

    op.create_table(
        "experiment_dataset_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("experiment_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("system_text", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_experiment_dataset_entries_experiment_id",
        "experiment_dataset_entries",
        ["experiment_id"],
    )

    op.create_table(
        "experiment_run_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("dataset_entry_id", sa.String(), nullable=False),
        sa.Column("eval_request_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["dataset_entry_id"],
            ["experiment_dataset_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["eval_request_id"], ["eval_requests.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_experiment_run_items_run_id", "experiment_run_items", ["run_id"]
    )


def downgrade() -> None:
    op.execute("SET lock_timeout = '4s'")
    op.execute("SET statement_timeout = '1min'")
    op.drop_table("experiment_run_items")
    op.drop_table("experiment_dataset_entries")
    op.drop_column("experiment_runs", "status")
    op.drop_column("experiments", "metrics")
