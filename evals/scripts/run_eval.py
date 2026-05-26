#!/usr/bin/env python3
"""
Eval runner. Loads the golden set, runs the QA pipeline directly (no HTTP),
computes deterministic metrics, and writes a JSONL result file.

Prerequisites:
  1. A contract indexed via POST /api/contracts/upload with status=ready.
  2. golden set entries updated with the correct contract_id (replace the null
     values in evals/golden/sample.jsonl with the real contract_id from step 1).
  3. API keys in .env (run from the backend/ directory or set PYTHONPATH).

Usage:
  cd backend
  uv run python ../evals/scripts/run_eval.py \\
      --golden ../evals/golden/sample.jsonl \\
      --results ../evals/results

The runner imports app modules directly so no server needs to be running.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add backend/ to the path so app.* imports work when run from the repo root.
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.citations import Citation, GoldSpan, compute_containment, validate_grounding
from app.config import get_settings
from app.db.session import get_session_factory
from app.evals import compute_retrieval_metrics
from app.evals.store import EvalResultEntry, save_results
from app.llm import Tier, get_llm_client
from app.observability import get_observability_client
from app.rerank import get_rerank_client
from app.retrieval import retrieve

import structlog

log = structlog.get_logger(__name__)

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


def _build_context(chunks: object) -> str:  # noqa: ANN001
    from app.db.models import Chunk
    parts: list[str] = []
    for c in chunks:  # type: ignore[union-attr]
        parts.append(f"[chunk_id: {c.id}] (page {c.page})\n{c.content}")
    return "\n\n---\n\n".join(parts)


def _extract_json(text: str) -> dict:  # type: ignore[type-arg]
    import json, re
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
    raise ValueError(f"No JSON in response: {stripped[:200]!r}")


def _is_refusal(answer: str) -> bool:
    lower = answer.lower()
    return any(phrase in lower for phrase in [
        "cannot find",
        "i don't know",
        "not mentioned",
        "not specified",
        "not provided",
        "no information",
        "unable to find",
    ])


async def _run_question(
    entry: dict,  # type: ignore[type-arg]
    session_factory: object,
    run_id: str,
) -> EvalResultEntry:
    from app.db.models import Chunk

    contract_id: str | None = entry.get("contract_id")
    question_id: str = entry["id"]
    question: str = entry["question"]
    bucket: str = entry["bucket"]
    cuad_category: str = entry.get("cuad_category", "")
    gold_answer: str = entry.get("gold_answer", "")
    gold_chunk_ids: list[str] = entry.get("gold_chunks", [])
    raw_spans: list[dict] = entry.get("gold_spans", [])  # type: ignore[assignment]
    gold_spans = [GoldSpan(text=s["text"], start=s.get("start")) for s in raw_spans]

    trace_id = str(uuid.uuid4())
    t0 = time.monotonic()

    if not contract_id:
        log.warning("run_eval.skip_no_contract_id", question_id=question_id)
        return EvalResultEntry(
            run_id=run_id,
            question_id=question_id,
            contract_id="",
            question=question,
            bucket=bucket,
            cuad_category=cuad_category,
            answer="",
            gold_answer=gold_answer,
            citations=[],
            gold_spans=[{"text": s.text} for s in gold_spans],
            retrieved_chunk_ids=[],
            gold_chunk_ids=gold_chunk_ids,
            recall_at_8=0.0,
            mrr_at_8=0.0,
            containment_precision=0.0,
            containment_recall=0.0,
            iou=None,
            latency_ms=0,
            trace_id=None,
            passed=False,
            failure_reason="contract_id not set — index a contract and update the golden set",
        )

    async with session_factory() as session:  # type: ignore[attr-defined]
        candidates = await retrieve(question, session, contract_id=contract_id)

    reranker = get_rerank_client()
    chunks = await reranker.rerank(question, candidates, top_k=8)

    retrieval_metrics = compute_retrieval_metrics(chunks, gold_spans)
    retrieved_ids = [c.id for c in chunks]

    if not chunks:
        latency_ms = int((time.monotonic() - t0) * 1000)
        passed = bucket == "C"  # no chunks + unanswerable = correct refusal
        return EvalResultEntry(
            run_id=run_id,
            question_id=question_id,
            contract_id=contract_id,
            question=question,
            bucket=bucket,
            cuad_category=cuad_category,
            answer="I cannot find relevant information in the provided contract excerpts.",
            gold_answer=gold_answer,
            citations=[],
            gold_spans=[{"text": s.text} for s in gold_spans],
            retrieved_chunk_ids=[],
            gold_chunk_ids=gold_chunk_ids,
            recall_at_8=0.0,
            mrr_at_8=0.0,
            containment_precision=0.0,
            containment_recall=0.0,
            iou=None,
            latency_ms=latency_ms,
            trace_id=trace_id,
            passed=passed,
            failure_reason="no_chunks_retrieved" if not passed else None,
        )

    context = _build_context(chunks)
    prompt = f"CONTRACT EXCERPTS:\n\n{context}\n\nQUESTION: {question}"

    llm = get_llm_client()
    raw = await llm.complete(prompt, Tier.SONNET, system=_QA_SYSTEM, max_tokens=1024, trace_id=trace_id)

    try:
        parsed = _extract_json(raw)
    except ValueError:
        parsed = {"answer": raw.strip(), "citations": [], "confidence": "low"}

    answer: str = str(parsed.get("answer", ""))
    raw_citations: list[dict] = parsed.get("citations", [])  # type: ignore[assignment]

    chunks_by_id: dict[str, Chunk] = {c.id: c for c in chunks}
    citations = [
        Citation(chunk_id=str(r.get("chunk_id", "")), quoted_text=str(r.get("quoted_text", "")))
        for r in raw_citations if r.get("chunk_id")
    ]
    grounding = validate_grounding(citations, chunks_by_id)
    grounded_chunks = [chunks_by_id[g.citation.chunk_id] for g in grounding if g.is_grounded and g.citation.chunk_id in chunks_by_id]

    containment = compute_containment(grounded_chunks, gold_spans)
    latency_ms = int((time.monotonic() - t0) * 1000)

    # Pass/fail rules per bucket
    if bucket == "C":
        # Unanswerable: model must refuse
        passed = _is_refusal(answer)
        failure_reason = "hallucinated_answer" if not passed else None
    else:
        # Answerable: recall and containment recall must both be 1.0
        passed = retrieval_metrics.recall_at_k >= 1.0 and containment.recall >= 1.0
        if not passed:
            reasons = []
            if retrieval_metrics.recall_at_k < 1.0:
                reasons.append("retrieval_miss")
            if containment.recall < 1.0:
                reasons.append("citation_miss")
            failure_reason = "+".join(reasons)
        else:
            failure_reason = None

    log.info(
        "run_eval.question_done",
        question_id=question_id,
        bucket=bucket,
        recall=retrieval_metrics.recall_at_k,
        containment_recall=containment.recall,
        passed=passed,
        latency_ms=latency_ms,
    )

    return EvalResultEntry(
        run_id=run_id,
        question_id=question_id,
        contract_id=contract_id,
        question=question,
        bucket=bucket,
        cuad_category=cuad_category,
        answer=answer,
        gold_answer=gold_answer,
        citations=[{"chunk_id": g.citation.chunk_id, "quoted_text": g.citation.quoted_text, "is_grounded": g.is_grounded} for g in grounding],
        gold_spans=[{"text": s.text, "start": s.start} for s in gold_spans],
        retrieved_chunk_ids=retrieved_ids,
        gold_chunk_ids=gold_chunk_ids,
        recall_at_8=retrieval_metrics.recall_at_k,
        mrr_at_8=retrieval_metrics.mrr_at_k,
        containment_precision=containment.precision,
        containment_recall=containment.recall,
        iou=None,  # bbox IoU requires annotation; computed separately
        latency_ms=latency_ms,
        trace_id=trace_id,
        passed=passed,
        failure_reason=failure_reason,
    )


async def main(golden_path: Path, results_dir: Path) -> None:
    settings = get_settings()
    obs = get_observability_client(settings)

    entries: list[dict] = []  # type: ignore[type-arg]
    with golden_path.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                entries.append(json.loads(line))

    log.info("run_eval.start", question_count=len(entries))

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    session_factory = get_session_factory()

    results: list[EvalResultEntry] = []
    for i, entry in enumerate(entries):
        result = await _run_question(entry, session_factory, run_id)
        results.append(result)
        if i < len(entries) - 1:
            # Voyage free tier: 3 RPM. Each question makes one embed call at
            # the start. Sleep 22s to stay safely under the limit.
            await asyncio.sleep(22)

    out_path = save_results(results, results_dir, run_id)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    log.info(
        "run_eval.done",
        passed=passed,
        total=total,
        pass_rate=round(passed / total, 3) if total else 0,
        results_file=str(out_path),
    )
    obs.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Clauseline eval harness")
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).parent.parent / "golden" / "sample.jsonl",
        help="Path to the golden set JSONL file",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path(__file__).parent.parent / "results",
        help="Directory to write result JSONL files",
    )
    args = parser.parse_args()
    asyncio.run(main(args.golden, args.results))
