import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    pass


class ContractStatus(enum.StrEnum):
    pending = "pending"
    indexing = "indexing"
    ready = "ready"
    error = "error"


class ChunkType(enum.StrEnum):
    section = "section"
    clause = "clause"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus, name="contractstatus"), nullable=False, default=ContractStatus.pending
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="contract", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[ChunkType] = mapped_column(
        SAEnum(ChunkType, name="chunktype"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Only clause-type chunks are embedded; section chunks have embedding=None
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    contract: Mapped["Contract"] = relationship("Contract", back_populates="chunks")


class DeviationRunStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class DeviationRun(Base):
    __tablename__ = "deviation_runs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[DeviationRunStatus] = mapped_column(
        SAEnum(DeviationRunStatus, name="deviationrunstatus"),
        nullable=False,
        default=DeviationRunStatus.pending,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
