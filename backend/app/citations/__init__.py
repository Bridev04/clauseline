"""
Deterministic citation validator. Every LLM answer includes a list of claimed
citation references (chunk ID + quoted text). This module verifies that each
citation maps to a real chunk retrieved in the same request (runtime grounding),
then exposes eval-time metrics (Spike 1 decision):

  Primary — Containment: does the cited chunk's text contain the gold span text
    as a substring? Robust to PDF layout variance and multi-span clauses where
    union-bbox IoU is inflated by whitespace. This is the CI gate metric.

  Secondary — Set-union IoU@0.5: used to measure visual Trust Panel highlight
    quality. Tracked but not CI-gated because ~15-20% of CUAD-style answers
    require multi-span citations where a single union bbox is geometrically
    misleading (Spike 1 finding).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Chunk


@dataclass
class Citation:
    chunk_id: str
    quoted_text: str  # exact text the LLM claims comes from this chunk


@dataclass
class GroundingResult:
    citation: Citation
    is_grounded: bool  # quoted_text found as substring in chunk.content
    chunk_page: int


@dataclass
class GoldSpan:
    text: str
    start: int | None = None  # char offset in the original document; optional


@dataclass
class GoldBbox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ContainmentMetrics:
    precision: float  # cited chunks containing ≥1 gold span / total cited chunks
    recall: float  # gold spans covered by ≥1 cited chunk / total gold spans
    cited_count: int
    gold_span_count: int


@dataclass
class IouMetrics:
    iou: float
    above_threshold: bool  # iou >= 0.5


def validate_grounding(
    citations: list[Citation],
    chunks_by_id: dict[str, Chunk],
) -> list[GroundingResult]:
    """Runtime grounding check: is each quoted_text actually in the cited chunk?

    Citations referencing an unknown chunk ID are marked not-grounded.
    Empty quoted_text is treated as not-grounded.
    """
    results: list[GroundingResult] = []
    for c in citations:
        chunk = chunks_by_id.get(c.chunk_id)
        if chunk is None:
            results.append(GroundingResult(citation=c, is_grounded=False, chunk_page=0))
            continue
        needle = c.quoted_text.strip()
        is_grounded = bool(needle) and needle in chunk.content
        results.append(
            GroundingResult(citation=c, is_grounded=is_grounded, chunk_page=chunk.page)
        )
    return results


def compute_containment(
    cited_chunks: list[Chunk],
    gold_spans: list[GoldSpan],
) -> ContainmentMetrics:
    """Eval-time containment precision and recall.

    Precision: fraction of cited chunks that contain at least one gold span text.
    Recall: fraction of gold spans whose text appears in at least one cited chunk.
    """
    if not cited_chunks or not gold_spans:
        return ContainmentMetrics(
            precision=0.0,
            recall=0.0,
            cited_count=len(cited_chunks),
            gold_span_count=len(gold_spans),
        )

    cited_texts = [c.content for c in cited_chunks]
    gold_texts = [s.text.strip() for s in gold_spans if s.text.strip()]

    precision_hits = sum(
        1 for ct in cited_texts if any(gt in ct for gt in gold_texts)
    )
    recall_hits = sum(
        1 for gt in gold_texts if any(gt in ct for ct in cited_texts)
    )

    return ContainmentMetrics(
        precision=precision_hits / len(cited_chunks),
        recall=recall_hits / len(gold_texts) if gold_texts else 0.0,
        cited_count=len(cited_chunks),
        gold_span_count=len(gold_texts),
    )


def _bbox_area(b: GoldBbox) -> float:
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def _bbox_intersection(a: GoldBbox, b: GoldBbox) -> float:
    if a.page != b.page:
        return 0.0
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    return max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)


def compute_iou(cited_bboxes: list[GoldBbox], gold_bboxes: list[GoldBbox]) -> IouMetrics:
    """Set-union IoU between cited bboxes and gold bboxes.

    Secondary metric — tracked but not CI-gated (Spike 1: geometrically
    misleading on multi-span clauses due to union bbox whitespace expansion).
    """
    if not cited_bboxes or not gold_bboxes:
        return IouMetrics(iou=0.0, above_threshold=False)

    intersection = sum(
        _bbox_intersection(c, g) for c in cited_bboxes for g in gold_bboxes
    )
    cited_area = sum(_bbox_area(b) for b in cited_bboxes)
    gold_area = sum(_bbox_area(b) for b in gold_bboxes)
    union = cited_area + gold_area - intersection
    iou = intersection / union if union > 0 else 0.0
    return IouMetrics(iou=round(iou, 4), above_threshold=iou >= 0.5)
