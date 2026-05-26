"""
Eval dashboard API. Read-only. The eval runner (evals/scripts/run_eval.py) writes
JSONL result files; these endpoints aggregate and serve them.

Week 3: /summary and /failures.
Week 4: /experiments.
Week 6: /ci-gate.
"""
from __future__ import annotations

import math
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import get_settings
from app.evals.store import EvalResultEntry, load_all_results

router = APIRouter()


def _load() -> list[EvalResultEntry]:
    return load_all_results(Path(get_settings().evals_results_dir))


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


class BucketSummary(BaseModel):
    bucket: str
    count: int
    recall_at_8: float
    containment_precision: float
    containment_recall: float
    pass_rate: float


class EvalSummaryResponse(BaseModel):
    total_questions: int
    pass_rate: float
    recall_at_8: float
    mrr_at_8: float
    containment_precision: float
    containment_recall: float
    per_bucket: list[BucketSummary]
    run_count: int


class FailureEntry(BaseModel):
    question_id: str
    contract_id: str
    question: str
    bucket: str
    cuad_category: str
    answer: str
    gold_answer: str
    citations: list[dict]  # type: ignore[type-arg]
    gold_spans: list[dict]  # type: ignore[type-arg]
    retrieved_chunk_ids: list[str]
    recall_at_8: float
    containment_precision: float
    containment_recall: float
    trace_id: str | None
    failure_reason: str | None
    timestamp: str


@router.get("/summary", response_model=EvalSummaryResponse)
async def get_summary() -> EvalSummaryResponse:
    """Headline metrics + per-bucket breakdown for the evals dashboard (Tab 1)."""
    results = _load()
    if not results:
        raise HTTPException(status_code=404, detail="No eval results found. Run the eval harness first.")

    run_ids = {r.run_id for r in results}

    buckets: dict[str, list[EvalResultEntry]] = {}
    for r in results:
        buckets.setdefault(r.bucket, []).append(r)

    per_bucket = [
        BucketSummary(
            bucket=b,
            count=len(entries),
            recall_at_8=_avg([e.recall_at_8 for e in entries]),
            containment_precision=_avg([e.containment_precision for e in entries]),
            containment_recall=_avg([e.containment_recall for e in entries]),
            pass_rate=_avg([float(e.passed) for e in entries]),
        )
        for b, entries in sorted(buckets.items())
    ]

    return EvalSummaryResponse(
        total_questions=len(results),
        pass_rate=_avg([float(r.passed) for r in results]),
        recall_at_8=_avg([r.recall_at_8 for r in results]),
        mrr_at_8=_avg([r.mrr_at_8 for r in results]),
        containment_precision=_avg([r.containment_precision for r in results]),
        containment_recall=_avg([r.containment_recall for r in results]),
        per_bucket=per_bucket,
        run_count=len(run_ids),
    )


@router.get("/failures", response_model=list[FailureEntry])
async def get_failures(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    bucket: str | None = Query(default=None, description="Filter by bucket: A, B, or C"),
) -> list[FailureEntry]:
    """Paginated failure explorer with retrieved chunks and Langfuse trace ID (Tab 2)."""
    results = _load()
    failures = [r for r in results if not r.passed]
    if bucket:
        failures = [f for f in failures if f.bucket == bucket]
    page = failures[offset : offset + limit]
    return [
        FailureEntry(
            question_id=r.question_id,
            contract_id=r.contract_id,
            question=r.question,
            bucket=r.bucket,
            cuad_category=r.cuad_category,
            answer=r.answer,
            gold_answer=r.gold_answer,
            citations=r.citations,
            gold_spans=r.gold_spans,
            retrieved_chunk_ids=r.retrieved_chunk_ids,
            recall_at_8=r.recall_at_8,
            containment_precision=r.containment_precision,
            containment_recall=r.containment_recall,
            trace_id=r.trace_id,
            failure_reason=r.failure_reason,
            timestamp=r.timestamp,
        )
        for r in page
    ]


class ExperimentDelta(BaseModel):
    pass_rate: float
    recall_at_8: float
    mrr_at_8: float
    containment_precision: float
    containment_recall: float


class ExperimentRun(BaseModel):
    run_id: str
    started_at: str
    question_count: int
    pass_rate: float
    recall_at_8: float
    mrr_at_8: float
    containment_precision: float
    containment_recall: float
    delta: ExperimentDelta | None = None


@router.get("/experiments", response_model=list[ExperimentRun])
async def get_experiments() -> list[ExperimentRun]:
    """Experiment timeline: one entry per run, sorted by start time, with metric deltas."""
    results = _load()
    if not results:
        return []

    runs: dict[str, list[EvalResultEntry]] = {}
    for r in results:
        runs.setdefault(r.run_id, []).append(r)

    summaries: list[tuple[str, ExperimentRun]] = []
    for run_id, entries in runs.items():
        started_at = min(e.timestamp for e in entries)
        summaries.append((started_at, ExperimentRun(
            run_id=run_id,
            started_at=started_at,
            question_count=len(entries),
            pass_rate=_avg([float(e.passed) for e in entries]),
            recall_at_8=_avg([e.recall_at_8 for e in entries]),
            mrr_at_8=_avg([e.mrr_at_8 for e in entries]),
            containment_precision=_avg([e.containment_precision for e in entries]),
            containment_recall=_avg([e.containment_recall for e in entries]),
        )))

    summaries.sort(key=lambda x: x[0])
    ordered = [run for _, run in summaries]

    for i in range(1, len(ordered)):
        prev, curr = ordered[i - 1], ordered[i]
        curr.delta = ExperimentDelta(
            pass_rate=round(curr.pass_rate - prev.pass_rate, 4),
            recall_at_8=round(curr.recall_at_8 - prev.recall_at_8, 4),
            mrr_at_8=round(curr.mrr_at_8 - prev.mrr_at_8, 4),
            containment_precision=round(curr.containment_precision - prev.containment_precision, 4),
            containment_recall=round(curr.containment_recall - prev.containment_recall, 4),
        )

    return ordered


# ---------------------------------------------------------------------------
# CI gate
# ---------------------------------------------------------------------------

_CI_GATE_METRICS = {"recall_at_8", "mrr_at_8", "containment_precision", "containment_recall", "pass_rate"}


class CIGateResponse(BaseModel):
    status: str  # "pass" | "fail" | "insufficient_data"
    metric: str
    threshold: float | None = None
    latest_value: float | None = None
    latest_run_id: str | None = None
    mean: float | None = None
    stddev: float | None = None
    run_count: int
    baseline_runs: int | None = None
    message: str | None = None


def _stddev(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


@router.get("/ci-gate", response_model=CIGateResponse)
async def ci_gate(
    metric: str = Query(default="recall_at_8", description="Metric to gate on"),
    min_runs: int = Query(default=3, ge=2, description="Minimum runs required for a baseline"),
) -> CIGateResponse:
    """Statistical CI gate: fail if the latest run is below mean - 1*stddev of prior runs."""
    if metric not in _CI_GATE_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric '{metric}'. Valid: {sorted(_CI_GATE_METRICS)}",
        )

    results = _load()
    if not results:
        return CIGateResponse(
            status="insufficient_data",
            metric=metric,
            run_count=0,
            message="No eval results found.",
        )

    run_groups: dict[str, list[EvalResultEntry]] = {}
    for e in results:
        run_groups.setdefault(e.run_id, []).append(e)

    run_summaries: list[tuple[str, float, str]] = []
    for run_id, run_entries in run_groups.items():
        avg = _avg([float(getattr(e, metric)) for e in run_entries])
        earliest = min(e.timestamp for e in run_entries)
        run_summaries.append((run_id, avg, earliest))

    run_summaries.sort(key=lambda x: x[2])
    run_count = len(run_summaries)

    if run_count < min_runs:
        return CIGateResponse(
            status="insufficient_data",
            metric=metric,
            run_count=run_count,
            message=f"Only {run_count} run(s); need {min_runs} for a baseline.",
        )

    baseline_values = [avg for _, avg, _ in run_summaries[:-1]]
    latest_run_id, latest_value, _ = run_summaries[-1]

    mean = _avg(baseline_values)
    stddev = _stddev(baseline_values, mean)
    threshold = mean - stddev

    return CIGateResponse(
        status="pass" if latest_value >= threshold else "fail",
        metric=metric,
        threshold=round(threshold, 4),
        latest_value=round(latest_value, 4),
        latest_run_id=latest_run_id,
        mean=round(mean, 4),
        stddev=round(stddev, 4),
        run_count=run_count,
        baseline_runs=len(baseline_values),
    )
