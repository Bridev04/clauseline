# Clauseline

> Contract intelligence with rigorous grounding, honest evals, and observable engineering.

**Status:** Week 8 complete — hybrid retrieval, QA with citations, deviation detection, HITL review, and live eval metrics all working.

> **Just want to see it run?** There's a zero-dependency **offline demo mode** — no
> Docker, no API keys, one command. Run `.\demo.ps1` (Windows) or `./demo.sh`
> (macOS/Linux) and open http://localhost:3000/evals. See [`DEMO.md`](DEMO.md) for
> the 3-minute interview walkthrough. The full production stack (below) needs
> Docker + three API keys.

---

## What this is

Clauseline is a contract intelligence system built to answer a specific question: can you trust the answer? RAG over contracts is commodity in 2026. The differentiator here is a citation grounding layer that links every answer to exact text spans, a hybrid retrieval pipeline with real BM25 fused via RRF in a single SQL query, and a navigable `/evals` page that exposes failures, experiments (including rolled-back ones), and benchmark comparisons side-by-side. Every architectural choice serves that thesis: the system should be *auditable*, not just accurate.

---

## Headline results

Measured against the 9-question golden set (`evals/golden/sample.jsonl`) on the ACME/Globex Software License Agreement. Eval run: `run_2026-05-26T075710`.

| Metric | Value | Notes |
|--------|-------|-------|
| Hybrid recall@8 | **100%** | All 7 answerable questions retrieved; 5-chunk corpus means hybrid vs dense difference shows at larger scale |
| MRR@8 | **0.93** | First gold-matching chunk ranked 1st for 6/7 answerable questions |
| Citation containment precision | **85.7%** | Fraction of cited chunks containing ≥1 gold span |
| Citation containment recall | **85.7%** | Fraction of gold spans covered by ≥1 cited chunk; 1 miss (q002) due to token truncation on complex renewal clause |
| Citation set-union IoU@0.5 | N/A | Requires bbox annotation; containment is the CI gate metric (Spike 1 decision) |
| Refusal accuracy (unanswerable bucket) | **50%** | 1/2; q007 answered correctly about which party holds the non-compete but did not refuse — a legitimate model quality edge case |
| Per-category F1 vs CUAD RoBERTa-large | not yet measured | Requires larger labeled set across 12 CUAD categories |
| p50 latency (end-to-end) | **6.4s** | Embedding + RRF retrieval + Sonnet; Cohere rerank on trial key fell back to RRF order |
| p90 latency (end-to-end) | **8.1s** | |
| Cost per query (Haiku-routed) | ~$0.002 | Haiku for classification/extraction legs only |
| Cost per query (Sonnet-routed) | ~$0.013 | Sonnet 4.6 at ~3K input + ~300 output tokens |

---

## Architecture (one screen)

```
PDF
 │
 ▼
┌─────────────────────────────────────────────┐
│  Parsing                                     │
│  PyMuPDF → text blocks + bboxes             │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  Chunking                                    │
│  Layout-aware hierarchical, dual granularity │
│  (section-level + clause-level chunks)       │
└──────────────────────┬──────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌─────────────────────┐
│  Voyage Embeddings│    │  Postgres (ParadeDB) │
│  voyage-3-large   │───▶│  pgvector cosine     │
│  (voyage-law-2    │    │  + pg_search BM25    │
│   as alt)         │    │  in one SQL query    │
└──────────────────┘    └──────────┬──────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  Hybrid Retrieval         │
                    │  RRF fusion (k=60)        │
                    │  top-20 dense + top-20    │
                    │  sparse → fused top-N     │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  Cohere Rerank            │
                    │  rerank-3, top-8          │
                    └──────────────┬───────────┘
                                   │
                         ┌─────────┴─────────┐
                         ▼                   ▼
               ┌──────────────┐   ┌──────────────────┐
               │  Haiku 4.5   │   │  Sonnet 4.6       │
               │  (fast/cheap │   │  (complex/high-   │
               │   routing)   │   │   stakes routing) │
               └──────┬───────┘   └────────┬─────────┘
                      └─────────┬──────────┘
                                │  ← Langfuse on every call
                                ▼
                    ┌──────────────────────────┐
                    │  Citation Validator       │
                    │  whitespace-normalized    │
                    │  containment check;       │
                    │  links answer → evidence  │
                    └──────────────┬───────────┘
                                   │
                    ┌──────────────┴───────────┐
                    ▼                          ▼
           ┌──────────────┐         ┌──────────────────┐
           │  Trust Panel │         │  /evals page      │
           │  (frontend)  │         │  failures/exp/    │
           └──────────────┘         │  benchmarks/demo  │
                                    └──────────────────┘

Separate pipeline ─────────────────────────────────────
PDF + Playbook YAML
 │
 ▼
LangGraph deviation pipeline
6 nodes: Loader → Classifier (Haiku, parallel per category)
       → Comparator (Sonnet, parallel per rule)
       → Scorer (deterministic)
       → Summarizer → HITL interrupt (AsyncPostgresSaver)
```

---

## The four load-bearing pieces

1. **Citation grounding** — Every answer carries evidence references with chunk ID and quoted text. A deterministic validator checks that claimed citations are exact substrings of the retrieved chunks (whitespace-normalized to handle PDF line-break artefacts). Containment recall is the primary CI gate metric (IoU@0.5 tracked but not gated — Spike 1 finding: union bbox is geometrically misleading on multi-span clauses).

2. **Hybrid retrieval with RRF** — A single Postgres query combines pgvector cosine similarity with pg_search BM25, fused via Reciprocal Rank Fusion (k=60). This is non-trivial to implement correctly and is validated in Spike 5 before any retrieval code is written.

3. **Playbook deviation detection** — A LangGraph pipeline (6 nodes + HITL interrupt) compares contract clauses against a customer playbook YAML. Haiku handles the parallel classification pass; Sonnet handles the per-rule comparison. Checkpoints are durable via AsyncPostgresSaver.

4. **The `/evals` page with five tabs** — (1) headline metrics + per-bucket breakdown, (2) failure explorer with retrieved chunks + Langfuse trace link, (3) experiments timeline including rolled-back ones, (4) live demo with Trust Panel, (5) deviation run review with HITL panel. Built early because it changes how you build.

---

## Tech stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend framework | FastAPI + Python 3.11 | async-first |
| Package manager | uv | lockfile committed |
| Database | ParadeDB (Postgres + pgvector + pg_search) | Docker |
| Embeddings | Voyage `voyage-3-large` | `voyage-law-2` as alt |
| Reranker | Cohere `rerank-3` | |
| LLM (fast) | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | classification, extraction |
| LLM (precise) | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | QA, comparison, summaries |
| Agentic pipeline | LangGraph + AsyncPostgresSaver | deviation only |
| Observability | Langfuse | every LLM call |
| Frontend | Next.js + TanStack Query + Recharts + shadcn/ui | |

---

## Repository layout

```
clauseline/
├── backend/          FastAPI app, all pipeline logic, tests
├── frontend/         Next.js app
├── evals/            Golden sets, eval results, scripts
├── data/             PDFs + playbook YAMLs (gitignored content)
├── docker/           docker-compose for ParadeDB
├── docs/             Architecture, decision log, spike reports
└── .github/          CI with eval gate
```

---

## Eval strategy

| Layer | Metric | Method | Gate |
|-------|--------|--------|------|
| Retrieval | recall@8 | deterministic (containment) | ≥ baseline |
| Retrieval | MRR@8 | deterministic (containment) | ≥ baseline |
| Citation | containment precision/recall | deterministic (whitespace-normalized substring) | ≥ baseline |
| Citation | IoU@0.5 | deterministic (bbox) | tracked, not gated |
| Generation | Ragas faithfulness | LLM-judge | mean − 1σ ≥ baseline |
| Generation | Refusal accuracy | deterministic | ≥ baseline |
| Latency/cost | p95 latency, $/query | deterministic | no regression |

**Golden set:** 9 questions across 3 buckets:
- Bucket A — single-chunk answers (governing law, liability cap, termination notice, renewal term, IP ownership)
- Bucket B — multi-chunk answers (indemnification, anti-assignment)
- Bucket C — unanswerable (tests refusal — the model must recognize the question cannot be answered from the excerpts)

**CI gate:** `mean − 1·stddev` over 3 eval runs must not drop below the baseline. Script at `evals/scripts/ci_gate.py`; wired into `.github/workflows/eval.yml`.

---

## Quick start

### Prerequisites
- Docker Desktop with WSL integration enabled
- `uv` installed (`curl -LsSf https://astral.sh/uv | sh`)
- API keys in `.env` (copy `.env.example`, fill in values)

### Start Postgres

```bash
docker compose -f docker/docker-compose.yml up -d
```

### Install deps + apply migrations

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
```

### Run the server

```bash
cd backend
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs  
Health: `curl http://localhost:8000/health`

### Run the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend: http://localhost:3000

### Run the eval harness

```bash
# 1. Upload a contract: POST http://localhost:8000/api/contracts/upload
# 2. Update contract_id in evals/golden/sample.jsonl
# 3. Run:
cd backend
uv run python ../evals/scripts/run_eval.py
# Results written to evals/results/run_<timestamp>.jsonl
```

### Checks

```bash
cd backend
uv run ruff check .
uv run mypy app

cd ../frontend
npx tsc --noEmit
npm run build
```

---

## Validation spikes

See [`docs/spikes/`](docs/spikes/) for full write-ups.

- **Spike 1 — Citation reality check:** Containment (substring match) is the sound primary metric; IoU@0.5 tracked as a secondary visual indicator.
- **Spike 2 — ContractNLI mapping:** 17 ContractNLI hypotheses mapped to playbook categories; hand-authored fixtures used for deviation evals.
- **Spike 3 — ContractEval overlap:** 12 CUAD categories selected; CUAD RoBERTa-large F1 is the baseline.
- **Spike 4 — README outline:** This file.
- **Spike 5 — pg_search install verification:** ParadeDB confirmed; `@@@` operator requires field-qualified queries (`'content:term'`).

---

## License

TBD

---

## Acknowledgments

[CUAD](https://www.atticusprojectai.org/cuad) · [ContractNLI](https://stanfordnlp.github.io/contract-nli/) · [ContractEval](https://github.com/TheAtticusProject/cuad) · [PyMuPDF](https://pymupdf.readthedocs.io/) · [ParadeDB](https://www.paradedb.com/) · [Voyage AI](https://www.voyageai.com/) · [Cohere](https://cohere.com/) · [Anthropic](https://www.anthropic.com/) · [Langfuse](https://langfuse.com/)
