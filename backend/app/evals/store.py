"""
JSONL-based eval result store. One file per eval run in evals/results/.
The API reads from this directory; the runner writes to it.
"""
from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class EvalResultEntry:
    run_id: str
    question_id: str
    contract_id: str
    question: str
    bucket: str  # A=single-chunk  B=multi-chunk  C=unanswerable
    cuad_category: str
    answer: str
    gold_answer: str
    citations: list[dict]  # type: ignore[type-arg]
    gold_spans: list[dict]  # type: ignore[type-arg]
    retrieved_chunk_ids: list[str]
    gold_chunk_ids: list[str]
    recall_at_8: float
    mrr_at_8: float
    containment_precision: float
    containment_recall: float
    iou: float | None
    latency_ms: int
    trace_id: str | None
    passed: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    failure_reason: str | None = None


def save_results(results: list[EvalResultEntry], results_dir: Path, run_id: str) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_id = run_id.replace(":", "-").replace("+", "").replace(" ", "_")
    out_path = results_dir / f"run_{safe_id}.jsonl"
    with out_path.open("w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")
    return out_path


def load_all_results(results_dir: Path) -> list[EvalResultEntry]:
    entries: list[EvalResultEntry] = []
    if not results_dir.exists():
        return entries
    for path in sorted(results_dir.glob("run_*.jsonl")):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(TypeError, KeyError):
                    entries.append(EvalResultEntry(**json.loads(line)))
    return entries
