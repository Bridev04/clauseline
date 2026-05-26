"""
Deterministic eval metrics. Retrieval and citation quality, computed without an
LLM judge. Ragas faithfulness / answer relevance are computed in the runner script
and attached to result entries after the fact.

Used by: evals/scripts/run_eval.py and app/api/evals.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.citations import GoldSpan, _norm
from app.db.models import Chunk


@dataclass
class RetrievalMetrics:
    recall_at_k: float  # ≥1 gold-matching chunk in the top-k?
    mrr_at_k: float  # 1/rank of the first gold-matching chunk; 0 if miss
    k: int


def compute_retrieval_metrics(
    retrieved_chunks: list[Chunk],
    gold_spans: list[GoldSpan],
) -> RetrievalMetrics:
    """Recall@k and MRR@k using content-containment as the match signal.

    A retrieved chunk "matches" if its content contains any gold span text as a
    substring. This works even when gold_chunk_ids are not pre-populated in the
    golden set (avoids the bootstrapping problem of needing to index first).
    """
    k = len(retrieved_chunks)
    if not retrieved_chunks or not gold_spans:
        return RetrievalMetrics(recall_at_k=0.0, mrr_at_k=0.0, k=k)

    gold_texts = [_norm(s.text) for s in gold_spans if s.text.strip()]
    if not gold_texts:
        return RetrievalMetrics(recall_at_k=0.0, mrr_at_k=0.0, k=k)

    first_rank: int | None = None
    for rank, chunk in enumerate(retrieved_chunks, start=1):
        if first_rank is None and any(gt in _norm(chunk.content) for gt in gold_texts):
            first_rank = rank

    recall = 1.0 if first_rank is not None else 0.0
    mrr = 1.0 / first_rank if first_rank is not None else 0.0
    return RetrievalMetrics(recall_at_k=recall, mrr_at_k=round(mrr, 4), k=k)
