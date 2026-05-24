"""
QA endpoint. Implements retrieve → rerank → LLM → grounding-validate pipeline.
Every citation in the response includes is_grounded=True/False so callers know
which evidence is anchored in the retrieved context.

Week 3.
"""
import json
import re
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.citations import Citation, GroundingResult, validate_grounding
from app.db.models import Chunk, Contract, ContractStatus
from app.db.session import get_session
from app.llm import Tier, get_llm_client
from app.observability import get_observability_client
from app.rerank import get_rerank_client
from app.retrieval import retrieve

log = structlog.get_logger(__name__)
router = APIRouter()

_QA_SYSTEM = """\
You are a contract analysis assistant. Answer the user's question using ONLY the provided contract excerpts.

Rules:
1. Use only the provided excerpts. If the answer is not present, set confidence to "none".
2. Cite evidence: for each claim, include the chunk_id and an exact quoted substring from that chunk.
3. Respond with a JSON object and nothing else:

{
  "answer": "Your answer here, or 'I cannot find this information in the provided contract excerpts.' if unanswerable",
  "citations": [
    {"chunk_id": "...", "quoted_text": "exact substring copied from the chunk"}
  ],
  "confidence": "high" | "medium" | "low" | "none"
}

Set confidence="none" and citations=[] when the question cannot be answered from the provided excerpts.\
"""


def _build_context(chunks: list[Chunk]) -> str:
    parts: list[str] = []
    for c in chunks:
        parts.append(f"[chunk_id: {c.id}] (page {c.page})\n{c.content}")
    return "\n\n---\n\n".join(parts)


def _extract_json(text: str) -> dict:  # type: ignore[type-arg]
    stripped = text.strip()
    try:
        return json.loads(stripped)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No JSON object found in LLM response: {stripped[:200]!r}")


class QARequest(BaseModel):
    contract_id: str
    question: str


class CitationOut(BaseModel):
    chunk_id: str
    quoted_text: str
    page: int
    is_grounded: bool


class QAResponse(BaseModel):
    contract_id: str
    question: str
    answer: str
    citations: list[CitationOut]
    confidence: str
    retrieved_count: int
    trace_id: str | None


@router.post("/ask", response_model=QAResponse)
async def ask(
    req: QARequest,
    session: AsyncSession = Depends(get_session),
) -> QAResponse:
    """Answer a question over a contract with grounding-validated citations."""
    t0 = time.monotonic()

    contract = (
        await session.execute(select(Contract).where(Contract.id == req.contract_id))
    ).scalar_one_or_none()
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.status != ContractStatus.ready:
        raise HTTPException(
            status_code=409,
            detail=f"Contract is not ready (status={contract.status.value})",
        )

    trace_id = str(uuid.uuid4())
    obs = get_observability_client()
    obs.trace(
        name="qa.ask",
        input={"contract_id": req.contract_id, "question": req.question},
        metadata={"trace_id": trace_id},
    )

    candidates = await retrieve(req.question, session, contract_id=req.contract_id)
    reranker = get_rerank_client()
    chunks = await reranker.rerank(req.question, candidates, top_k=8)

    if not chunks:
        log.info("qa.no_chunks", contract_id=req.contract_id, trace_id=trace_id)
        return QAResponse(
            contract_id=req.contract_id,
            question=req.question,
            answer="I cannot find relevant information in the provided contract excerpts.",
            citations=[],
            confidence="none",
            retrieved_count=0,
            trace_id=trace_id,
        )

    context = _build_context(chunks)
    prompt = f"CONTRACT EXCERPTS:\n\n{context}\n\nQUESTION: {req.question}"

    llm = get_llm_client()
    raw = await llm.complete(
        prompt,
        Tier.SONNET,
        system=_QA_SYSTEM,
        max_tokens=1024,
        trace_id=trace_id,
    )

    try:
        parsed = _extract_json(raw)
    except ValueError:
        log.warning("qa.json_parse_failed", raw_preview=raw[:200], trace_id=trace_id)
        parsed = {"answer": raw.strip(), "citations": [], "confidence": "low"}

    answer: str = str(parsed.get("answer", ""))
    confidence: str = str(parsed.get("confidence", "low"))
    raw_citations: list[dict[str, object]] = parsed.get("citations", [])

    chunks_by_id: dict[str, Chunk] = {c.id: c for c in chunks}
    citations = [
        Citation(
            chunk_id=str(r.get("chunk_id", "")),
            quoted_text=str(r.get("quoted_text", "")),
        )
        for r in raw_citations
        if r.get("chunk_id")
    ]
    grounding: list[GroundingResult] = validate_grounding(citations, chunks_by_id)

    latency_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "qa.done",
        contract_id=req.contract_id,
        retrieved=len(chunks),
        citations=len(citations),
        grounded=sum(1 for g in grounding if g.is_grounded),
        confidence=confidence,
        latency_ms=latency_ms,
        trace_id=trace_id,
    )

    return QAResponse(
        contract_id=req.contract_id,
        question=req.question,
        answer=answer,
        citations=[
            CitationOut(
                chunk_id=g.citation.chunk_id,
                quoted_text=g.citation.quoted_text,
                page=g.chunk_page,
                is_grounded=g.is_grounded,
            )
            for g in grounding
        ],
        confidence=confidence,
        retrieved_count=len(chunks),
        trace_id=trace_id,
    )
