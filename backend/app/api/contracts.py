from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import chunk_blocks
from app.db.models import Chunk, ChunkType, Contract, ContractStatus
from app.db.session import get_session
from app.embeddings import get_embedding_client
from app.parsing import parse_pdf

router = APIRouter()
log = structlog.get_logger(__name__)

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_contract(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()

    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="File is not a valid PDF")

    # Parse first to get the hash for dedup check
    parse_result = parse_pdf(file_bytes)

    existing = await session.scalar(
        select(Contract).where(Contract.file_hash == parse_result.file_hash)
    )
    if existing is not None:
        return {"contract_id": existing.id, "chunk_count": 0, "duplicate": True}

    filename = file.filename or "unknown.pdf"
    log.info("contracts.upload.start", filename=filename, size=len(file_bytes))

    contract = Contract(
        filename=filename,
        file_hash=parse_result.file_hash,
        page_count=parse_result.page_count,
        status=ContractStatus.indexing,
    )
    session.add(contract)
    await session.flush()  # get contract.id before embedding loop

    try:
        all_chunks = chunk_blocks(parse_result.blocks)

        # Only clause chunks get embeddings — they are the QA retrieval unit
        clause_data = [cd for cd in all_chunks if cd.chunk_type == "clause"]
        section_data = [cd for cd in all_chunks if cd.chunk_type == "section"]

        embeddings = await get_embedding_client().embed([cd.content for cd in clause_data])

        chunks: list[Chunk] = []
        for cd, emb in zip(clause_data, embeddings, strict=True):
            chunks.append(
                Chunk(
                    contract_id=contract.id,
                    content=cd.content,
                    chunk_type=ChunkType.clause,
                    page=cd.page,
                    bbox=cd.bbox,
                    token_count=cd.token_count,
                    embedding=emb,
                )
            )
        for cd in section_data:
            chunks.append(
                Chunk(
                    contract_id=contract.id,
                    content=cd.content,
                    chunk_type=ChunkType.section,
                    page=cd.page,
                    bbox=cd.bbox,
                    token_count=cd.token_count,
                    embedding=None,
                )
            )

        session.add_all(chunks)
        contract.status = ContractStatus.ready
        await session.commit()

        log.info("contracts.upload.done", contract_id=contract.id, chunk_count=len(chunks))
        return {
            "contract_id": contract.id,
            "filename": filename,
            "page_count": parse_result.page_count,
            "chunk_count": len(chunks),
        }

    except Exception:
        contract.status = ContractStatus.error
        await session.commit()
        log.exception("contracts.upload.failed", contract_id=contract.id)
        raise HTTPException(status_code=500, detail="Failed to process contract")


@router.get("/")
async def list_contracts(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = await session.scalars(select(Contract).order_by(Contract.uploaded_at.desc()))
    return [
        {
            "contract_id": c.id,
            "filename": c.filename,
            "page_count": c.page_count,
            "status": c.status.value,
            "uploaded_at": c.uploaded_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/{contract_id}")
async def get_contract(
    contract_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    chunk_count = await session.scalar(
        sa.select(sa.func.count(Chunk.id)).where(Chunk.contract_id == contract_id)
    )
    return {
        "contract_id": contract.id,
        "filename": contract.filename,
        "page_count": contract.page_count,
        "status": contract.status.value,
        "uploaded_at": contract.uploaded_at.isoformat(),
        "chunk_count": chunk_count or 0,
    }
