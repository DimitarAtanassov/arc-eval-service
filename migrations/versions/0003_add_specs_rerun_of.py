"""add specs + rerun_of to evaluations

Records now persist the judge specs used (``specs``) and link re-runs to their
parent evaluation (``rerun_of``). ``specs`` is NOT NULL with a ``[]`` server
default so existing rows upgrade cleanly.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-29

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
    op.add_column(
        "evaluations",
        sa.Column(
            "specs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "evaluations",
        sa.Column("rerun_of", sa.String(), nullable=True),
    )
    op.create_index("ix_evaluations_rerun_of", "evaluations", ["rerun_of"])


def downgrade() -> None:
    op.drop_index("ix_evaluations_rerun_of", table_name="evaluations")
    op.drop_column("evaluations", "rerun_of")
    op.drop_column("evaluations", "specs")
