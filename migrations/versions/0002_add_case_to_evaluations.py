"""add case column to evaluations

Persists the scored interaction alongside the record so the row is
self-describing and read-only consumers (arc-platform) can reconstruct the
request and its trace. Nullable for backward compatibility with existing rows.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluations",
        sa.Column("case", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluations", "case")
