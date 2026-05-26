"""HITL review columns for deviation_runs

Adds awaiting_review to the deviationrunstatus enum and three review
columns: review_decision, review_notes, reviewed_at.

Note: ALTER TYPE ... ADD VALUE cannot run inside a PostgreSQL transaction
block, so we commit, run the DDL, then begin a new transaction before the
column additions.

Revision ID: 0003_hitl_review
Revises: 0002_deviation_runs
Create Date: 2026-05-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0003_hitl_review"
down_revision: str | None = "0002_deviation_runs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    # ADD VALUE cannot run inside a transaction; commit, run, restart.
    conn.execute(text("COMMIT"))
    conn.execute(text("ALTER TYPE deviationrunstatus ADD VALUE IF NOT EXISTS 'awaiting_review'"))
    conn.execute(text("BEGIN"))

    op.add_column("deviation_runs", sa.Column("review_decision", sa.Text(), nullable=True))
    op.add_column("deviation_runs", sa.Column("review_notes", sa.Text(), nullable=True))
    op.add_column(
        "deviation_runs",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deviation_runs", "reviewed_at")
    op.drop_column("deviation_runs", "review_notes")
    op.drop_column("deviation_runs", "review_decision")
    # Removing a value from a PG enum requires recreating the type;
    # downgrade only removes the columns and leaves the enum value in place.
