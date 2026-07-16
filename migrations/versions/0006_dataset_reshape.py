"""dataset evaluator reshape: drop the model-running experiment columns

Contract step of the dataset-evaluator refactor (0005 was the additive expand). Now
that an experiment owns a metric set and a dataset, and runs link to their scores
through experiment_run_items, drop the columns the old model-running experiment used:
experiments.model_name/generation_config/prompt_template/variables and
experiment_runs.inference_id/eval_request_id.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-15

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail fast rather than queue behind a long-running query. Column drops are
    # metadata-only, so the lock is brief.
    op.execute("SET lock_timeout = '4s'")
    op.execute("SET statement_timeout = '1min'")
    op.drop_column("experiment_runs", "eval_request_id")
    op.drop_column("experiment_runs", "inference_id")
    op.drop_column("experiments", "variables")
    op.drop_column("experiments", "prompt_template")
    op.drop_column("experiments", "generation_config")
    op.drop_column("experiments", "model_name")


def downgrade() -> None:
    # Schema reversibility only; the dropped data is not restored. The recreated
    # columns are nullable or defaulted so the downgrade cannot fail on existing rows.
    op.execute("SET lock_timeout = '4s'")
    op.execute("SET statement_timeout = '1min'")
    op.add_column(
        "experiments",
        sa.Column("model_name", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "experiments",
        sa.Column(
            "generation_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "experiments", sa.Column("prompt_template", sa.String(), nullable=True)
    )
    op.add_column(
        "experiments",
        sa.Column(
            "variables",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "experiment_runs", sa.Column("inference_id", sa.String(), nullable=True)
    )
    op.add_column(
        "experiment_runs", sa.Column("eval_request_id", sa.String(), nullable=True)
    )
