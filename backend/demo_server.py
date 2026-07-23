#!/usr/bin/env python3
"""
Clauseline — DEMO SERVER (zero dependencies, offline).

This is a self-contained stand-in for the real FastAPI backend, built for live
demos and interviews. It speaks the exact same HTTP API the Next.js frontend
calls, but needs NO Docker, NO ParadeDB, and NO API keys — just the Python
standard library. Nothing here reaches the network.

Where possible it serves the project's *real* data:
  * /api/evals/*   → aggregated from the real JSONL run files in evals/results/
  * /api/qa/ask    → grounded answers curated from the golden set + a real eval run
  * /api/deviation → a realistic seeded pipeline result you can review live

The real, production pipeline lives in app/ (hybrid retrieval, LangGraph
deviation graph, citation grounding). This file exists only so the whole thing
is demonstrable in one command when the full stack (Docker + 3 paid APIs) is not
practical to stand up — e.g. mid-interview.

Run:  python demo_server.py           (listens on http://localhost:8000)
"""
from __future__ import annotations

import contextlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

HERE = Path(__file__).resolve().parent          # backend/
REPO = HERE.parent                              # clauseline/
RESULTS_DIR = REPO / "evals" / "results"

HOST = "0.0.0.0"
PORT = 8000

# --------------------------------------------------------------------------- #
# Seed data
# --------------------------------------------------------------------------- #

DEMO_CONTRACT_ID = "d22ff386-4765-48a3-b87a-50a7feff232a"
DEMO_CONTRACT_FILENAME = "acme_globex_software_license_agreement_sample.pdf"

CONTRACTS: list[dict] = [
    {
        "contract_id": DEMO_CONTRACT_ID,
        "filename": DEMO_CONTRACT_FILENAME,
        "page_count": 3,
        "status": "ready",
        "uploaded_at": "2026-05-26T07:40:00+00:00",
        "chunk_count": 5,
    }
]

PLAYBOOKS: list[dict] = [
    {
        "id": "saas-procurement-v2",
        "name": "SaaS Procurement Standard",
        "version": "2.0",
        "description": "Buyer-side playbook for inbound SaaS/software licenses — "
        "governing law, liability caps, IP, indemnity, assignment.",
        "rule_count": 6,
    },
    {
        "id": "eval-fixture-v1",
        "name": "Eval Fixture Playbook",
        "version": "1.0",
        "description": "Minimal playbook used as a fixture in the eval harness.",
        "rule_count": 5,
    },
]

# Curated, grounded QA answers keyed by a normalized question.
# Quotes are real excerpts from the ACME/Globex sample; chunk ids and pages
# mirror the indexed contract so the Trust Panel renders authentically.
_QA: list[dict] = [
    {
        "match": ["governing law"],
        "question": "What is the governing law of this agreement?",
        "answer": "This Agreement is governed by the laws of the State of Delaware, "
        "without regard to conflict of law principles. Any disputes must be brought "
        "in the state or federal courts located in Delaware — this contract uses "
        "litigation, not arbitration.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "8294d9cd-5ef0-42eb-822a-40a03611b52d",
                "quoted_text": "This Agreement shall be governed by and construed in "
                "accordance with the laws of the State of Delaware, without regard to "
                "conflict of law principles.",
                "page": 3,
                "is_grounded": True,
            }
        ],
    },
    {
        "match": ["initial term", "renew", "renewal term"],
        "question": "What is the initial term of the agreement and when does it renew?",
        "answer": "The initial term is one year from the Effective Date. The agreement "
        "then automatically renews for successive one-year terms unless either party "
        "gives written notice of non-renewal at least 90 days before the end of the "
        "then-current term.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "07212c2d-ad44-43d0-885e-30695580c476",
                "quoted_text": "this Agreement will automatically renew for successive "
                "one-year renewal terms unless either party gives written notice of "
                "non-renewal at least 90 days before the end of the then-current term.",
                "page": 1,
                "is_grounded": True,
            }
        ],
    },
    {
        "match": ["cap on liability", "liability cap", "cap on", "limitation of liability"],
        "question": "What is the cap on liability in this agreement?",
        "answer": "Each party's total liability is capped at the total fees paid by the "
        "Licensee in the 12 months preceding the claim. Neither party is liable for "
        "indirect, incidental, special, consequential, or punitive damages. The cap "
        "does not apply to confidentiality breaches, indemnification obligations, "
        "willful misconduct, or payment obligations.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "8294d9cd-5ef0-42eb-822a-40a03611b52d",
                "quoted_text": "each party's total liability arising out of this "
                "Agreement shall not exceed the total fees paid by Licensee to Licensor "
                "under this Agreement in the 12 months preceding the claim.",
                "page": 2,
                "is_grounded": True,
            },
            {
                "chunk_id": "8294d9cd-5ef0-42eb-822a-40a03611b52d",
                "quoted_text": "Neither party shall be liable for indirect, incidental, "
                "special, consequential, or punitive damages.",
                "page": 2,
                "is_grounded": True,
            },
        ],
    },
    {
        "match": ["intellectual property", "owns the", "ip ownership", "who owns"],
        "question": "Who owns the intellectual property, and does ownership transfer to the licensee?",
        "answer": "The Licensor retains all right, title, and interest in the Software, "
        "including all intellectual property rights, updates, improvements, and "
        "derivative works. The Licensee does not acquire ownership. Any feedback the "
        "Licensee provides may be used by the Licensor without restriction or compensation.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "8294d9cd-5ef0-42eb-822a-40a03611b52d",
                "quoted_text": "Licensor retains all right, title, and interest in and to "
                "the Software, including all intellectual property rights, updates, "
                "improvements, modifications, and derivative works. Licensee does not "
                "acquire ownership of the Software.",
                "page": 2,
                "is_grounded": True,
            }
        ],
    },
    {
        "match": ["indemnif"],
        "question": "What indemnification obligations does each party have?",
        "answer": "The Licensor must indemnify the Licensee against third-party claims "
        "that the Software infringes a United States patent, copyright, or trademark. "
        "The Licensee must indemnify the Licensor against third-party claims arising "
        "from the Licensee's unauthorized use of the Software, violation of law, or "
        "breach of this Agreement. Indemnification is carved out of the liability cap.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "8294d9cd-5ef0-42eb-822a-40a03611b52d",
                "quoted_text": "Licensor shall indemnify, defend, and hold harmless "
                "Licensee from third-party claims alleging that the Software infringes "
                "any United States patent, copyright, or trademark.",
                "page": 2,
                "is_grounded": True,
            },
            {
                "chunk_id": "8294d9cd-5ef0-42eb-822a-40a03611b52d",
                "quoted_text": "Licensee shall indemnify, defend, and hold harmless "
                "Licensor from third-party claims arising from Licensee's unauthorized "
                "use of the Software, violation of law, or breach of this Agreement.",
                "page": 2,
                "is_grounded": True,
            },
        ],
    },
    {
        "match": ["anti-assignment", "assign or transfer", "assignment"],
        "question": "What are the anti-assignment provisions and what exceptions apply?",
        "answer": "Neither party may assign or transfer the Agreement without the other "
        "party's prior written consent, except to an affiliate or in connection with a "
        "merger, acquisition, corporate reorganization, or sale of substantially all "
        "assets. Any attempted assignment in violation is void. A change of control is "
        "deemed an assignment requiring written notice within 30 days.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "4606c5e1-d3ec-446e-8348-5f8a9300614c",
                "quoted_text": "Neither party may assign or transfer this Agreement "
                "without the prior written consent of the other party, except to an "
                "affiliate or in connection with a merger, acquisition, corporate "
                "reorganization, or sale of substantially all assets.",
                "page": 3,
                "is_grounded": True,
            }
        ],
    },
    {
        "match": ["terminate for convenience", "termination for convenience"],
        "question": "Under what circumstances can either party terminate for convenience, and what notice is required?",
        "answer": "Either party may terminate the Agreement for convenience upon 90 days' "
        "prior written notice to the other party. No cause or specific circumstances are "
        "required — the notice period is the only condition.",
        "confidence": "high",
        "citations": [
            {
                "chunk_id": "07212c2d-ad44-43d0-885e-30695580c476",
                "quoted_text": "Either party may terminate this Agreement for convenience "
                "upon 90 days' prior written notice.",
                "page": 1,
                "is_grounded": True,
            }
        ],
    },
    {
        "match": ["licensor", "vendor", "compet"],
        "question": "Does this agreement restrict the Licensor (vendor) from competing after termination?",
        "answer": "No — I cannot find a restriction on the Licensor. The non-compete in "
        "Section 9 restricts only the Licensee from building a competing product for one "
        "year after termination. There is no equivalent post-termination restriction on "
        "the Licensor (the vendor).",
        "confidence": "low",
        "citations": [
            {
                "chunk_id": "4606c5e1-d3ec-446e-8348-5f8a9300614c",
                "quoted_text": "During the Term and for one year after termination, "
                "Licensee shall not use the Software to develop, market, or provide a "
                "competing software product that performs substantially similar analytics "
                "functions.",
                "page": 3,
                "is_grounded": True,
            }
        ],
    },
    {
        "match": ["arbitration"],
        "question": "What is the arbitration venue and the governing arbitration rules?",
        "answer": "I cannot find this information in the provided contract excerpts. This "
        "agreement does not contain an arbitration clause — disputes are resolved in the "
        "state or federal courts located in Delaware.",
        "confidence": "none",
        "citations": [],
    },
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _seed_deviation_runs() -> list[dict]:
    """One completed run (approved) and one awaiting review, so the tab is alive."""
    base = datetime.now(UTC)

    awaiting_result = {
        "contract_id": DEMO_CONTRACT_ID,
        "playbook_id": "saas-procurement-v2",
        "comparisons": [
            {
                "rule_category": "cap_on_liability",
                "rule_severity": "high",
                "label": "Deviating",
                "deviation_type": "Wrong Value",
                "evidence_text": "each party's total liability ... shall not exceed the "
                "total fees paid by Licensee ... in the 12 months preceding the claim.",
            },
            {
                "rule_category": "uncapped_liability",
                "rule_severity": "critical",
                "label": "Deviating",
                "deviation_type": "Forbidden Clause",
                "evidence_text": "Except for confidentiality breaches, indemnification "
                "obligations, willful misconduct, or payment obligations ...",
            },
            {
                "rule_category": "anti_assignment",
                "rule_severity": "medium",
                "label": "Unclear",
                "deviation_type": "Ambiguous Language",
                "evidence_text": "A change of control of either party shall be deemed an "
                "assignment requiring written notice to the other party within 30 days.",
            },
        ],
        "score": {
            "overall_severity": "critical",
            "per_rule": [
                {"category": "cap_on_liability", "severity": "high", "deviation_type": "Wrong Value", "label": "Deviating"},
                {"category": "uncapped_liability", "severity": "critical", "deviation_type": "Forbidden Clause", "label": "Deviating"},
                {"category": "anti_assignment", "severity": "medium", "deviation_type": "Ambiguous Language", "label": "Unclear"},
            ],
        },
        "summary": (
            "## Deviation review — ACME/Globex SLA vs. SaaS Procurement Standard\n\n"
            "**Overall risk: CRITICAL.** Three rules deviate from the buyer-side playbook, "
            "one of them critical.\n\n"
            "1. **Uncapped-liability carve-outs (critical).** The liability section carves "
            "confidentiality breaches, indemnification, willful misconduct, and payment "
            "obligations *out* of the cap. Our playbook forbids uncapped exposure; these "
            "carve-outs create unbounded liability and must be negotiated to a super-cap.\n\n"
            "2. **Liability cap value (high).** The cap is 12 months of trailing fees. The "
            "playbook standard is the greater of 24 months' fees or a fixed floor. Push for "
            "a higher multiple.\n\n"
            "3. **Change-of-control notice (medium, unclear).** Assignment on change of "
            "control is allowed with 30 days' notice but the consent mechanics are "
            "ambiguous. Clarify whether consent can be withheld.\n\n"
            "**Recommended next step:** counter on the liability carve-outs first — that is "
            "the only critical item and the highest-leverage point of the negotiation."
        ),
    }

    completed_result = {
        "contract_id": DEMO_CONTRACT_ID,
        "playbook_id": "eval-fixture-v1",
        "comparisons": [
            {
                "rule_category": "confidentiality",
                "rule_severity": "medium",
                "label": "Unclear",
                "deviation_type": "Partial Compliance",
                "evidence_text": "Each party shall protect the other's Confidential "
                "Information with reasonable care.",
            }
        ],
        "score": {
            "overall_severity": "medium",
            "per_rule": [
                {"category": "confidentiality", "severity": "medium", "deviation_type": "Partial Compliance", "label": "Unclear"},
            ],
        },
        "summary": (
            "## Deviation review — ACME/Globex SLA vs. Eval Fixture Playbook\n\n"
            "**Overall risk: MEDIUM.** The contract satisfies governing-law, liability-cap, "
            "and termination requirements. One item is only partially compliant: the "
            "confidentiality clause specifies 'reasonable care' but no survival period. "
            "Recommend adding an explicit post-termination survival term (e.g. 3 years)."
        ),
    }

    return [
        {
            "run_id": str(uuid.uuid4()),
            "contract_id": DEMO_CONTRACT_ID,
            "playbook_id": "saas-procurement-v2",
            "status": "awaiting_review",
            "overall_severity": "critical",
            "deviations_found": 3,
            "result": awaiting_result,
            "review_decision": None,
            "review_notes": None,
            "reviewed_at": None,
            "created_at": (base - timedelta(minutes=4)).isoformat(),
            "updated_at": (base - timedelta(minutes=4)).isoformat(),
        },
        {
            "run_id": str(uuid.uuid4()),
            "contract_id": DEMO_CONTRACT_ID,
            "playbook_id": "eval-fixture-v1",
            "status": "completed",
            "overall_severity": "medium",
            "deviations_found": 1,
            "result": completed_result,
            "review_decision": "approved",
            "review_notes": "Confirmed — flag survival period in redlines.",
            "reviewed_at": (base - timedelta(hours=1)).isoformat(),
            "created_at": (base - timedelta(hours=1, minutes=6)).isoformat(),
            "updated_at": (base - timedelta(hours=1)).isoformat(),
        },
    ]


# In-memory run store (mutated by POST /run and POST /{id}/review).
DEVIATION_RUNS: list[dict] = _seed_deviation_runs()

# --------------------------------------------------------------------------- #
# Eval aggregation (mirrors app/api/evals.py, reading real JSONL run files)
# --------------------------------------------------------------------------- #


def _load_results() -> list[dict]:
    entries: list[dict] = []
    if not RESULTS_DIR.exists():
        return entries
    for path in sorted(RESULTS_DIR.glob("run_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    entries.append(json.loads(line))
    return entries


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _stddev(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return variance ** 0.5


def eval_summary() -> dict:
    all_results = _load_results()
    if not all_results:
        return {"__status__": 404, "detail": "No eval results found. Run the eval harness first."}

    run_ids = {r["run_id"] for r in all_results}

    # Headline reflects the LATEST run, not a blend of every run. Blending an
    # older pre-fix run into the top-line metrics understates the current
    # system; the cross-run trend lives on the Experiments tab instead.
    by_run: dict[str, list[dict]] = {}
    for r in all_results:
        by_run.setdefault(r["run_id"], []).append(r)
    latest_run_id = max(by_run, key=lambda rid: min(e["timestamp"] for e in by_run[rid]))
    results = by_run[latest_run_id]

    buckets: dict[str, list[dict]] = {}
    for r in results:
        buckets.setdefault(r["bucket"], []).append(r)

    per_bucket = [
        {
            "bucket": b,
            "count": len(entries),
            "recall_at_8": _avg([e["recall_at_8"] for e in entries]),
            "containment_precision": _avg([e["containment_precision"] for e in entries]),
            "containment_recall": _avg([e["containment_recall"] for e in entries]),
            "pass_rate": _avg([float(e["passed"]) for e in entries]),
        }
        for b, entries in sorted(buckets.items())
    ]

    return {
        "total_questions": len(results),
        "pass_rate": _avg([float(r["passed"]) for r in results]),
        "recall_at_8": _avg([r["recall_at_8"] for r in results]),
        "mrr_at_8": _avg([r["mrr_at_8"] for r in results]),
        "containment_precision": _avg([r["containment_precision"] for r in results]),
        "containment_recall": _avg([r["containment_recall"] for r in results]),
        "per_bucket": per_bucket,
        "run_count": len(run_ids),
    }


def eval_failures(limit: int, offset: int, bucket: str | None) -> list[dict]:
    results = _load_results()
    failures = [r for r in results if not r["passed"]]
    if bucket:
        failures = [f for f in failures if f["bucket"] == bucket]
    page = failures[offset : offset + limit]
    keys = [
        "question_id", "contract_id", "question", "bucket", "cuad_category",
        "answer", "gold_answer", "citations", "gold_spans", "retrieved_chunk_ids",
        "recall_at_8", "containment_precision", "containment_recall", "trace_id",
        "failure_reason", "timestamp",
    ]
    return [{k: r.get(k) for k in keys} for r in page]


def eval_experiments() -> list[dict]:
    results = _load_results()
    if not results:
        return []

    runs: dict[str, list[dict]] = {}
    for r in results:
        runs.setdefault(r["run_id"], []).append(r)

    summaries: list[tuple[str, dict]] = []
    for run_id, entries in runs.items():
        started_at = min(e["timestamp"] for e in entries)
        summaries.append((started_at, {
            "run_id": run_id,
            "started_at": started_at,
            "question_count": len(entries),
            "pass_rate": _avg([float(e["passed"]) for e in entries]),
            "recall_at_8": _avg([e["recall_at_8"] for e in entries]),
            "mrr_at_8": _avg([e["mrr_at_8"] for e in entries]),
            "containment_precision": _avg([e["containment_precision"] for e in entries]),
            "containment_recall": _avg([e["containment_recall"] for e in entries]),
            "delta": None,
        }))

    summaries.sort(key=lambda x: x[0])
    ordered = [run for _, run in summaries]
    for i in range(1, len(ordered)):
        prev, curr = ordered[i - 1], ordered[i]
        curr["delta"] = {
            "pass_rate": round(curr["pass_rate"] - prev["pass_rate"], 4),
            "recall_at_8": round(curr["recall_at_8"] - prev["recall_at_8"], 4),
            "mrr_at_8": round(curr["mrr_at_8"] - prev["mrr_at_8"], 4),
            "containment_precision": round(curr["containment_precision"] - prev["containment_precision"], 4),
            "containment_recall": round(curr["containment_recall"] - prev["containment_recall"], 4),
        }
    return ordered


_CI_METRICS = {"recall_at_8", "mrr_at_8", "containment_precision", "containment_recall", "pass_rate"}


def eval_ci_gate(metric: str, min_runs: int) -> dict:
    if metric not in _CI_METRICS:
        return {"__status__": 400, "detail": f"Unknown metric '{metric}'."}
    results = _load_results()
    if not results:
        return {"status": "insufficient_data", "metric": metric, "run_count": 0,
                "message": "No eval results found."}

    groups: dict[str, list[dict]] = {}
    for e in results:
        groups.setdefault(e["run_id"], []).append(e)

    run_summaries = []
    for run_id, entries in groups.items():
        avg = _avg([float(e[metric]) for e in entries])
        earliest = min(e["timestamp"] for e in entries)
        run_summaries.append((run_id, avg, earliest))
    run_summaries.sort(key=lambda x: x[2])
    run_count = len(run_summaries)

    if run_count < min_runs:
        return {"status": "insufficient_data", "metric": metric, "run_count": run_count,
                "message": f"Only {run_count} run(s); need {min_runs} for a baseline."}

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


# --------------------------------------------------------------------------- #
# QA
# --------------------------------------------------------------------------- #


def _normalize(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", q.lower())


def answer_question(contract_id: str, question: str) -> dict:
    norm = _normalize(question)
    best: dict | None = None
    best_score = 0
    for entry in _QA:
        score = sum(1 for kw in entry["match"] if kw in norm)
        if score > best_score:
            best_score = score
            best = entry

    trace_id = str(uuid.uuid4())
    if best is None or best_score == 0:
        return {
            "contract_id": contract_id,
            "question": question,
            "answer": "I cannot find this information in the provided contract excerpts. "
            "Try one of the suggested questions to see grounded evidence.",
            "citations": [],
            "confidence": "none",
            "retrieved_count": 5,
            "trace_id": trace_id,
        }

    return {
        "contract_id": contract_id,
        "question": question,
        "answer": best["answer"],
        "citations": best["citations"],
        "confidence": best["confidence"],
        "retrieved_count": 5,
        "trace_id": trace_id,
    }


# --------------------------------------------------------------------------- #
# Deviation mutations
# --------------------------------------------------------------------------- #


def start_deviation_run(contract_id: str, playbook_id: str) -> dict:
    pb = next((p for p in PLAYBOOKS if p["id"] == playbook_id), None)
    playbook_name = pb["name"] if pb else playbook_id
    now = datetime.now(UTC)
    result = {
        "contract_id": contract_id,
        "playbook_id": playbook_id,
        "comparisons": [
            {
                "rule_category": "cap_on_liability",
                "rule_severity": "high",
                "label": "Deviating",
                "deviation_type": "Wrong Value",
                "evidence_text": "total liability ... shall not exceed the total fees paid "
                "by Licensee ... in the 12 months preceding the claim.",
            },
            {
                "rule_category": "uncapped_liability",
                "rule_severity": "critical",
                "label": "Deviating",
                "deviation_type": "Forbidden Clause",
                "evidence_text": "Except for confidentiality breaches, indemnification "
                "obligations, willful misconduct, or payment obligations ...",
            },
        ],
        "score": {
            "overall_severity": "critical",
            "per_rule": [
                {"category": "cap_on_liability", "severity": "high", "deviation_type": "Wrong Value", "label": "Deviating"},
                {"category": "uncapped_liability", "severity": "critical", "deviation_type": "Forbidden Clause", "label": "Deviating"},
            ],
        },
        "summary": (
            f"## Deviation review — {playbook_name}\n\n"
            "**Overall risk: CRITICAL.** Two liability rules deviate from the playbook. "
            "The liability cap is only 12 months of trailing fees (playbook wants 24), and "
            "several obligations are carved out of the cap entirely, creating uncapped "
            "exposure. Recommend countering on the carve-outs first.\n"
        ),
    }
    run = {
        "run_id": str(uuid.uuid4()),
        "contract_id": contract_id,
        "playbook_id": playbook_id,
        "status": "awaiting_review",
        "overall_severity": "critical",
        "deviations_found": 2,
        "result": result,
        "review_decision": None,
        "review_notes": None,
        "reviewed_at": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    DEVIATION_RUNS.insert(0, run)
    return run


def review_deviation_run(run_id: str, decision: str, edited_summary, notes) -> dict:
    run = next((r for r in DEVIATION_RUNS if r["run_id"] == run_id), None)
    if run is None:
        return {"__status__": 404, "detail": "Deviation run not found"}
    if run["status"] != "awaiting_review":
        return {"__status__": 409, "detail": f"Run is not awaiting review (status={run['status']})"}

    if edited_summary and isinstance(run["result"], dict):
        run["result"]["summary"] = edited_summary
    run["status"] = "completed"
    run["review_decision"] = decision
    run["review_notes"] = notes
    run["reviewed_at"] = _now_iso()
    run["updated_at"] = _now_iso()
    return run


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #

_DOCS_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Clauseline demo API</title>
<style>body{font:15px/1.6 system-ui,sans-serif;max-width:760px;margin:48px auto;padding:0 20px;color:#18181b}
code{background:#f4f4f5;padding:2px 6px;border-radius:4px;font-size:13px}
h1{margin-bottom:4px}.tag{display:inline-block;background:#fef3c7;color:#92400e;font-size:12px;
padding:2px 8px;border-radius:999px;font-weight:600}li{margin:4px 0}</style></head>
<body><h1>Clauseline <span class="tag">DEMO MODE</span></h1>
<p>Zero-dependency offline stand-in for the FastAPI backend. No Docker, no API keys.
Eval metrics are aggregated from the project's real run files; QA answers are curated
from the golden set.</p>
<h3>Endpoints</h3><ul>
<li><code>GET /health</code></li>
<li><code>GET /api/contracts/</code></li>
<li><code>POST /api/qa/ask</code> &nbsp;<code>{contract_id, question}</code></li>
<li><code>GET /api/evals/summary</code></li>
<li><code>GET /api/evals/failures?bucket=A|B|C</code></li>
<li><code>GET /api/evals/experiments</code></li>
<li><code>GET /api/evals/ci-gate?metric=recall_at_8</code></li>
<li><code>GET /api/playbooks/</code></li>
<li><code>GET /api/deviation/runs</code></li>
<li><code>POST /api/deviation/run</code> &nbsp;<code>{contract_id, playbook_id}</code></li>
<li><code>POST /api/deviation/{run_id}/review</code> &nbsp;<code>{decision, edited_summary?, notes?}</code></li>
</ul>
<p>Open the dashboard at <a href="http://localhost:3000/evals">localhost:3000/evals</a>.</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"  {self.command} {self.path.split('?')[0]}")

    # -- helpers -----------------------------------------------------------
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, payload, status: int = 200) -> None:
        if isinstance(payload, dict) and "__status__" in payload:
            status = payload.pop("__status__")
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    # -- verbs -------------------------------------------------------------
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        def q(name: str, default: str) -> str:
            return qs.get(name, [default])[0]

        if path == "/" or path == "/docs":
            return self._send_html(_DOCS_HTML)
        if path == "/health":
            return self._send_json({"status": "ok", "env": "demo", "version": "0.1.0-demo"})
        if path == "/api/contracts":
            return self._send_json(CONTRACTS)
        if path == "/api/playbooks":
            return self._send_json(PLAYBOOKS)
        if path == "/api/evals/summary":
            return self._send_json(eval_summary())
        if path == "/api/evals/failures":
            return self._send_json(eval_failures(int(q("limit", "50")), int(q("offset", "0")),
                                                 qs.get("bucket", [None])[0]))
        if path == "/api/evals/experiments":
            return self._send_json(eval_experiments())
        if path == "/api/evals/ci-gate":
            return self._send_json(eval_ci_gate(q("metric", "recall_at_8"), int(q("min_runs", "3"))))
        if path == "/api/deviation/runs":
            limit = int(q("limit", "20"))
            status = qs.get("status", [None])[0]
            runs = DEVIATION_RUNS
            if status:
                runs = [r for r in runs if r["status"] == status]
            return self._send_json(runs[:limit])

        m = re.match(r"^/api/contracts/([^/]+)$", path)
        if m:
            cid = m.group(1)
            c = next((x for x in CONTRACTS if x["contract_id"] == cid), None)
            return self._send_json(c or {"__status__": 404, "detail": "Contract not found"})

        m = re.match(r"^/api/deviation/runs/([^/]+)$", path)
        if m:
            r = next((x for x in DEVIATION_RUNS if x["run_id"] == m.group(1)), None)
            return self._send_json(r or {"__status__": 404, "detail": "Deviation run not found"})

        self._send_json({"__status__": 404, "detail": f"Not found: {path}"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self._read_body()

        if path == "/api/qa/ask":
            return self._send_json(answer_question(
                body.get("contract_id", DEMO_CONTRACT_ID), body.get("question", "")))

        if path == "/api/contracts/upload":
            # Demo: accept anything, hand back the pre-indexed sample contract.
            return self._send_json({
                "contract_id": DEMO_CONTRACT_ID,
                "filename": DEMO_CONTRACT_FILENAME,
                "page_count": 3,
                "chunk_count": 5,
                "duplicate": True,
            }, status=201)

        if path == "/api/deviation/run":
            return self._send_json(start_deviation_run(
                body.get("contract_id", DEMO_CONTRACT_ID),
                body.get("playbook_id", "saas-procurement-v2")))

        m = re.match(r"^/api/deviation/([^/]+)/review$", path)
        if m:
            return self._send_json(review_deviation_run(
                m.group(1), body.get("decision", "approved"),
                body.get("edited_summary"), body.get("notes")))

        self._send_json({"__status__": 404, "detail": f"Not found: {path}"})


def main() -> None:
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print("=" * 64)
        print(f"  Could not start on port {PORT}: {exc}")
        print(f"  Something is already using port {PORT} — likely an old demo")
        print("  backend still running. Close it, then try again.")
        print("=" * 64)
        raise SystemExit(1) from exc

    n_results = len(list(RESULTS_DIR.glob("run_*.jsonl"))) if RESULTS_DIR.exists() else 0
    print("=" * 64)
    print("  Clauseline DEMO backend  —  offline, no keys, no Docker")
    print("=" * 64)
    print(f"  Listening on   http://localhost:{PORT}")
    print(f"  API docs       http://localhost:{PORT}/docs")
    print(f"  Eval runs      {n_results} file(s) from {RESULTS_DIR.relative_to(REPO)}")
    print("  Dashboard      http://localhost:3000/evals  (start the frontend)")
    print("  Ctrl+C to stop")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Demo backend stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
