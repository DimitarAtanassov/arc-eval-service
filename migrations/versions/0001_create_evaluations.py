"""create evaluations table

Revision ID: 0001
Revises:
Create Date: 2026-06-28

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
        "evaluations",
        sa.Column("evaluation_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("aggregate_score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("evaluation_id"),
    )
    op.create_index(
        "ix_evaluations_request_id", "evaluations", ["request_id"]
    )
    op.create_index(
        "ix_evaluations_created_at", "evaluations", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_evaluations_created_at", table_name="evaluations")
    op.drop_index("ix_evaluations_request_id", table_name="evaluations")
    op.drop_table("evaluations")
