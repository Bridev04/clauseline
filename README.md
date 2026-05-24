# Clauseline

> Contract intelligence with rigorous grounding, honest evals, and observable engineering.

**Status:** 🚧 Pre-Week-1 (running validation spikes — see [`docs/spikes/`](docs/spikes/))

---

## What this is

Clauseline is a contract intelligence system built to answer a specific question: can you trust the answer? RAG over contracts is commodity in 2026. The differentiator here is a citation grounding layer that returns bounding-box–linked evidence, a hybrid retrieval pipeline with real BM25 fused via RRF in a single SQL query, and — most importantly — a navigable `/evals` page that exposes failures, experiments (including rolled-back ones), and benchmark comparisons side-by-side. Every architectural choice serves that thesis: the system should be *auditable*, not just accurate.

---

## Headline results

> Values are TBD — populated after Week 3+ eval runs. The table structure is intentional: if you can't name the metric before building, you don't know what you're building.

| Metric | Value | Notes |
|--------|-------|-------|
| Hybrid vs dense recall@8 | TBD | RRF k=60, top-8 after rerank |
| Citation containment precision | TBD | cited chunk contains gold span (primary metric — see Spike 1) |
| Citation containment recall | TBD | |
| Citation set-union IoU@0.5 | TBD | visual quality indicator; not the CI gate |
| Ragas faithfulness | TBD | LLM-judge, mean − 1σ over 3 runs |
| Refusal accuracy (unanswerable bucket) | TBD | 20-question bucket |
| Per-category F1 vs CUAD RoBERTa-large baseline | TBD | 12 CUAD categories (Spike 3) |
| p95 latency (single-chunk query) | TBD | end-to-end including rerank |
| Cost per query (Haiku-routed) | TBD | |
| Cost per query (Sonnet-routed) | TBD | |

---

## Architecture (one screen)

```
PDF
 │
 ▼
┌─────────────────────────────────────────────┐
│  Parsing                                     │
│  PyMuPDF4LLM (primary) → markdown + bboxes  │
│  LlamaParse (fallback for scans/complex)     │
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
                    │  deterministic bbox IoU   │
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
5 nodes: Loader → Classifier (Haiku, parallel per category)
       → Comparator (Sonnet, parallel per rule)
       → Scorer (deterministic)
       → Summarizer → HITL interrupt
```

---

## The four load-bearing pieces

1. **Citation grounding with bbox + IoU** — Every answer carries evidence references that include page number and bounding box coordinates from the source PDF. A deterministic validator checks that claimed citations actually overlap the retrieved chunks. IoU@0.5 is the primary citation quality metric.

2. **Hybrid retrieval with RRF** — A single Postgres query combines pgvector cosine similarity with pg_search BM25, fused via Reciprocal Rank Fusion (k=60). This is non-trivial to implement correctly and is validated in Spike 5 before any retrieval code is written.

3. **Playbook deviation detection** — A LangGraph pipeline (5 nodes + human-in-the-loop interrupt) compares contract clauses against a customer's playbook YAML. Haiku handles the parallel classification pass; Sonnet handles the per-rule comparison.

4. **The `/evals` page with four tabs** — (1) headline metrics + per-bucket breakdown, (2) failure explorer with retrieved chunks + Langfuse trace link, (3) experiments timeline including rolled-back ones, (4) live demo with Trust Panel. Built early because it changes how you build.

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
| Agentic pipeline | LangGraph | deviation only |
| Observability | Langfuse | every LLM call |
| Frontend | Next.js + TanStack Query + Recharts + shadcn/ui | Week 3+ |

---

## Repository layout

```
clauseline/
├── backend/          FastAPI app, all pipeline logic, tests
├── frontend/         Next.js app (scaffolded Week 3)
├── evals/            Golden sets, eval results, scripts
├── data/             PDFs + playbook YAMLs (gitignored content)
├── docker/           docker-compose for ParadeDB
├── docs/             Architecture, decision log, spike reports
└── .github/          CI + future eval gate
```

---

## Eval strategy (preview)

| Layer | Metric | Method | Gate |
|-------|--------|--------|------|
| Retrieval | recall@8 | deterministic | ≥ baseline |
| Retrieval | MRR@8 | deterministic | ≥ baseline |
| Citation | IoU@0.5 precision/recall | deterministic (bbox) | ≥ baseline |
| Generation | Ragas faithfulness | LLM-judge | mean − 1σ ≥ baseline |
| Generation | Ragas answer relevance | LLM-judge | mean − 1σ ≥ baseline |
| Generation | Refusal accuracy | deterministic | ≥ baseline |
| Latency/cost | p95 latency, $/query | deterministic | no regression |

**Golden set:** 60 questions across 3 buckets of 20:
- Bucket A — single-chunk answers (clean retrieval signal)
- Bucket B — multi-chunk answers (requires synthesis across passages)
- Bucket C — unanswerable (tests refusal; model must say "I don't know")

**Merge gate:** `mean − 1·stddev` over 3 LLM-judge runs must not drop below the baseline JSON in `evals/results/baseline.json`. Deterministic metrics must not regress at all. Gate lands in CI Week 6.

---

## Pre-Week-1 validation spikes

See [`docs/spikes/`](docs/spikes/) for full templates and decision rules.

- **Spike 1 — Citation reality check:** Do real contract Q&A answers map to single bboxes or require set-union? Determines whether IoU@0.5 is a sound metric or needs redesign.
- **Spike 2 — ContractNLI mapping:** How well do the 17 ContractNLI hypotheses map to our target playbook categories? Determines whether we use ContractNLI as a dev fixture or hand-author cases.
- **Spike 3 — ContractEval overlap:** What 12 CUAD categories appear in ContractEval's test set? The *output* of this spike is our final category list.
- **Spike 4 — README outline:** ✅ DONE — this file is the deliverable.
- **Spike 5 — pg_search install verification:** Does the ParadeDB image support the exact SQL syntax for fused pgvector + pg_search + RRF? Must validate before writing any retrieval code.

---

## Quick start

> ⚠️ Not runnable yet — application code lands Week 1+.

```bash
# Backend
cd backend
uv sync
docker compose -f ../docker/docker-compose.yml up -d
uv run uvicorn app.main:app --reload

# Frontend (Week 3+)
cd frontend
pnpm install
pnpm dev
```

---

## License

TBD

---

## Acknowledgments

[CUAD](https://www.atticusprojectai.org/cuad) · [ContractNLI](https://stanfordnlp.github.io/contract-nli/) · [ContractEval](https://github.com/TheAtticusProject/cuad) · [PyMuPDF](https://pymupdf.readthedocs.io/) · [ParadeDB](https://www.paradedb.com/) · [Voyage AI](https://www.voyageai.com/) · [Cohere](https://cohere.com/) · [Anthropic](https://www.anthropic.com/) · [Langfuse](https://langfuse.com/)
