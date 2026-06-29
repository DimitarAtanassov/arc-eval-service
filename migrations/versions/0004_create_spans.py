"""create spans table

The collector fans OTel spans to this service; they are normalised and persisted
here so the control plane can render real trace trees (identity, lineage, timing
and ``arc.*`` attributes) for both inference and evaluation. Keyed on ``span_id``
for idempotent upserts; ``trace_id`` indexed because reads fetch a whole trace.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-29

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
    op.create_table(
        "spans",
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("parent_span_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("start_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("end_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("span_id"),
    )
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_service_name", "spans", ["service_name"])
    op.create_index("ix_spans_ingested_at", "spans", ["ingested_at"])


def downgrade() -> None:
    op.drop_index("ix_spans_ingested_at", table_name="spans")
    op.drop_index("ix_spans_service_name", table_name="spans")
    op.drop_index("ix_spans_trace_id", table_name="spans")
    op.drop_table("spans")
