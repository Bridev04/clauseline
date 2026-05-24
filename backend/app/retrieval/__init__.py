"""
Hybrid retrieval via a single Postgres query. Combines pgvector cosine similarity
(`<=>` operator) and pg_search BM25 (`@@@` operator) using Reciprocal Rank Fusion
with k=60. Top-20 dense candidates and top-20 sparse candidates are fused in one
SQL CTE, avoiding a round-trip. The fused list is passed to the rerank layer.

Spike 5 confirmed (2026-05-24): pg_search 0.23.4 + vector 0.8.1 on ParadeDB latest.
Non-obvious syntax constraint: the `@@@` operator requires field-qualified queries
(`'content:term'`), not bare terms (`'term'`). Use space-separated terms for OR
semantics: `'content:governing content:law'`.

Implemented: Week 2.
"""
import re
from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Chunk
from app.embeddings import EmbeddingClient, get_embedding_client

log = structlog.get_logger(__name__)


@dataclass
class RetrievalResult:
    chunk: Chunk
    rrf_score: float


def _build_bm25_query(query_text: str) -> str:
    """Build a pg_search field-qualified query from free text.

    pg_search requires 'content:term' syntax. Space-separated terms are OR.
    Returns empty string if no usable tokens are found — callers should skip
    the sparse leg when this returns empty.
    """
    tokens = re.findall(r"[a-zA-Z0-9]+", query_text.lower())
    tokens = [t for t in tokens if len(t) > 2]
    if not tokens:
        return ""
    return " ".join(f"content:{t}" for t in tokens)


def _vec_to_pg(embedding: list[float]) -> str:
    """Format a float list as a pgvector literal '[f1,f2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


async def retrieve(
    query: str,
    session: AsyncSession,
    *,
    contract_id: str | None = None,
    settings: Settings | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> list[RetrievalResult]:
    """Fused dense+sparse retrieval with RRF scoring.

    Returns up to dense_k + sparse_k candidates (deduplicated by chunk ID),
    sorted descending by RRF score. Pass the result to rerank() to select the
    final top-k for the LLM context window.

    Only clause chunks (those with an embedding) participate in retrieval.
    """
    cfg = settings or get_settings()
    ec = embedding_client or get_embedding_client()

    [query_embedding] = await ec.embed([query])
    query_vec = _vec_to_pg(query_embedding)
    bm25_query = _build_bm25_query(query)

    dense_k = cfg.retrieval_top_k_dense
    sparse_k = cfg.retrieval_top_k_sparse
    rrf_k = cfg.rrf_k

    # Optional contract-scoped filter — built as a literal SQL fragment because
    # it's derived from Python logic, not user input.
    contract_filter = "AND contract_id = :contract_id" if contract_id else ""

    ctes: list[str] = [
        f"""
        dense AS (
            SELECT id,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_vec AS vector)) AS rank
            FROM chunks
            WHERE embedding IS NOT NULL {contract_filter}
            ORDER BY embedding <=> CAST(:query_vec AS vector)
            LIMIT {dense_k}
        )"""
    ]

    if bm25_query:
        ctes.append(
            f"""
        sparse AS (
            SELECT id,
                   ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS rank
            FROM chunks
            WHERE chunks @@@ :bm25_query {contract_filter}
            LIMIT {sparse_k}
        )"""
        )
        union_src = "SELECT id, rank FROM dense UNION ALL SELECT id, rank FROM sparse"
    else:
        union_src = "SELECT id, rank FROM dense"

    ctes.append(
        f"""
        rrf AS (
            SELECT id,
                   SUM(1.0 / ({rrf_k}.0 + rank)) AS rrf_score
            FROM ({union_src}) sub
            GROUP BY id
        )"""
    )

    sql = text(
        "WITH " + ",\n".join(ctes) + "\nSELECT id, rrf_score FROM rrf ORDER BY rrf_score DESC"
    )

    params: dict[str, str] = {"query_vec": query_vec}
    if bm25_query:
        params["bm25_query"] = bm25_query
    if contract_id:
        params["contract_id"] = contract_id

    rows = (await session.execute(sql, params)).fetchall()
    if not rows:
        log.info("retrieval.empty", query_len=len(query), contract_id=contract_id)
        return []

    score_by_id = {row.id: float(row.rrf_score) for row in rows}
    chunk_ids = list(score_by_id)

    chunks_result = await session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    chunks_by_id = {c.id: c for c in chunks_result.scalars().all()}

    results = [
        RetrievalResult(chunk=chunks_by_id[cid], rrf_score=score_by_id[cid])
        for cid in chunk_ids
        if cid in chunks_by_id
    ]

    log.info(
        "retrieval.done",
        query_len=len(query),
        contract_id=contract_id,
        candidates=len(results),
        has_sparse=bool(bm25_query),
    )
    return results
