"""experiment prompt template and variables

Adds the prompt configuration to experiments so a run frames its input through a
named arc-model-lab prompt template. prompt_template is nullable (an experiment
without one sends raw input); variables is a JSONB map, default {}, that fills the
template's non-input placeholders. Additive and backward compatible: existing
experiments get a NULL template and an empty variables map, so they keep sending
raw input.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail fast rather than queue behind a long-running query. Both adds are
    # metadata-only (a nullable column and a column with a constant default), so
    # neither rewrites the table.
    op.execute("SET lock_timeout = '4s'")
    op.execute("SET statement_timeout = '1min'")
    op.add_column("experiments", sa.Column("prompt_template", sa.String(), nullable=True))
    op.add_column(
        "experiments",
        sa.Column(
            "variables",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.execute("SET lock_timeout = '4s'")
    op.execute("SET statement_timeout = '1min'")
    op.drop_column("experiments", "variables")
    op.drop_column("experiments", "prompt_template")
