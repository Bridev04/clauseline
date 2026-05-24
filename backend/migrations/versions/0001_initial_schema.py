"""initial schema: contracts, chunks, vector + bm25 indexes

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Pre-installed in ParadeDB — IF NOT EXISTS makes this safe to re-run
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    op.create_table(
        "contracts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "indexing", "ready", "error", name="contractstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("contract_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "chunk_type",
            sa.Enum("section", "clause", name="chunktype"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # IVFFlat for approximate cosine-distance nearest-neighbor search
    op.execute(
        "CREATE INDEX IF NOT EXISTS chunks_embedding_ivfflat "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # BM25 for pg_search full-text search (Spike 5 confirmed syntax)
    # key_field must be the PK column name; queries require field:term format
    op.execute(
        "CREATE INDEX IF NOT EXISTS chunks_bm25 "
        "ON chunks USING bm25 (id, content) WITH (key_field='id')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_bm25")
    op.execute("DROP INDEX IF EXISTS chunks_embedding_ivfflat")
    op.drop_table("chunks")
    op.drop_table("contracts")
    op.execute("DROP TYPE IF EXISTS chunktype")
    op.execute("DROP TYPE IF EXISTS contractstatus")
