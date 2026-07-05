"""drop eval_requests.task_type

The evaluate contract no longer classifies interactions by task type; callers
name the metrics to score explicitly. Drop the now-unused column.

Revision ID: 0002_drop_task_type
Revises: 0001
Create Date: 2026-07-05

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_drop_task_type"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail fast rather than queue behind a long-running query on eval_requests.
    op.execute("SET lock_timeout = '3s'")
    op.drop_column("eval_requests", "task_type")


def downgrade() -> None:
    op.execute("SET lock_timeout = '3s'")
    # Re-add with a server default so backfilling existing rows is instant, then
    # drop the default to restore the original (defaultless) NOT NULL column.
    op.add_column(
        "eval_requests",
        sa.Column("task_type", sa.String(), nullable=False, server_default="unknown"),
    )
    op.alter_column("eval_requests", "task_type", server_default=None)
