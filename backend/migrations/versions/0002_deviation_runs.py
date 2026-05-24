"""deviation_runs table

Revision ID: 0002_deviation_runs
Revises: 0001_initial
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_deviation_runs"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deviation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("contract_id", sa.String(), nullable=False),
        sa.Column("playbook_id", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="deviationrunstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_deviation_runs_contract_id", "deviation_runs", ["contract_id"])
    op.create_index("ix_deviation_runs_playbook_id", "deviation_runs", ["playbook_id"])


def downgrade() -> None:
    op.drop_index("ix_deviation_runs_playbook_id", table_name="deviation_runs")
    op.drop_index("ix_deviation_runs_contract_id", table_name="deviation_runs")
    op.drop_table("deviation_runs")
    op.execute("DROP TYPE IF EXISTS deviationrunstatus")
