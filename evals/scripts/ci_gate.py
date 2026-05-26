#!/usr/bin/env python
"""
Eval CI gate: fail if the latest eval run falls below mean - 1*stddev of prior runs.

Self-contained — reads JSONL directly, no backend dependencies.

Usage (from repo root):
    python evals/scripts/ci_gate.py [--metric recall_at_8] [--min-runs 3] [--results-dir PATH]

Exit codes:
    0 — gate passes (or insufficient history)
    1 — gate fails (latest run is a statistically significant regression)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

VALID_METRICS = [
    "recall_at_8",
    "mrr_at_8",
    "containment_precision",
    "containment_recall",
    "pass_rate",
]

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[2] / "evals" / "results"


def _load_runs(results_dir: Path) -> dict[str, list[dict[str, object]]]:
    """Load all JSONL result files and group entries by run_id."""
    groups: dict[str, list[dict[str, object]]] = {}
    if not results_dir.exists():
        return groups
    for path in sorted(results_dir.glob("run_*.jsonl")):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    run_id = entry.get("run_id", "unknown")
                    groups.setdefault(str(run_id), []).append(entry)
                except json.JSONDecodeError:
                    continue
    return groups


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def compute_gate(
    results_dir: Path,
    metric: str,
    min_runs: int,
) -> dict[str, object]:
    """Return gate result dict. Does not exit — caller decides."""
    run_groups = _load_runs(results_dir)

    if not run_groups:
        return {
            "status": "insufficient_data",
            "message": "No eval results found.",
            "run_count": 0,
        }

    # Compute per-run metric average + earliest timestamp for sorting
    run_summaries: list[tuple[str, float, str]] = []
    for run_id, entries in run_groups.items():
        values = [float(e[metric]) for e in entries if metric in e]  # type: ignore[arg-type]
        avg = _avg(values) if values else 0.0
        earliest = min((str(e.get("timestamp", "")), ) for e in entries)[0]
        run_summaries.append((run_id, avg, earliest))

    run_summaries.sort(key=lambda x: x[2])
    run_count = len(run_summaries)

    if run_count < min_runs:
        return {
            "status": "insufficient_data",
            "message": f"Only {run_count} run(s); need {min_runs} for a baseline. Gate passes.",
            "run_count": run_count,
            "metric": metric,
        }

    baseline = [avg for _, avg, _ in run_summaries[:-1]]
    latest_run_id, latest_value, _ = run_summaries[-1]

    mean = _avg(baseline)
    stddev = _stddev(baseline, mean)
    threshold = mean - stddev

    return {
        "status": "pass" if latest_value >= threshold else "fail",
        "metric": metric,
        "threshold": round(threshold, 4),
        "latest_value": round(latest_value, 4),
        "latest_run_id": latest_run_id,
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "run_count": run_count,
        "baseline_runs": len(baseline),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval CI gate (mean - 1*stddev)")
    parser.add_argument(
        "--metric",
        default="recall_at_8",
        choices=VALID_METRICS,
        help="Metric to gate on (default: recall_at_8)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=3,
        metavar="N",
        help="Minimum number of runs before the gate activates (default: 3)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Path to eval results directory",
    )
    args = parser.parse_args()

    result = compute_gate(
        results_dir=args.results_dir,
        metric=args.metric,
        min_runs=args.min_runs,
    )

    status = str(result["status"])

    if status == "insufficient_data":
        print(f"[CI GATE] SKIP — {result['message']}")
        print(f"  runs found: {result['run_count']}, min required: {args.min_runs}")
        sys.exit(0)

    print(f"[CI GATE] {'PASS' if status == 'pass' else 'FAIL'} — metric={result['metric']}")
    print(f"  threshold (mean - 1*stddev): {result['threshold']}")
    print(f"  latest run:                  {result['latest_value']}  ({result['latest_run_id']})")
    print(f"  baseline mean:               {result['mean']}")
    print(f"  baseline stddev:             {result['stddev']}")
    print(f"  runs in baseline:            {result['baseline_runs']} of {result['run_count']} total")

    if status == "fail":
        print()
        print("  !! Regression detected. Latest run fell below the statistical threshold.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
