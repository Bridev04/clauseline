# Clauseline — Project CLAUDE.md

## What this is

Contract intelligence portfolio project: hybrid retrieval (pgvector + pg_search BM25 + RRF),
QA with citations, and a deviation-detection pipeline. Frontend scaffolded in Week 3.

---

## Current state

**Phase: Week 3 complete** (as of 2026-05-24)

All 5 pre-Week-1 validation spikes are done (see `docs/spikes/`).
Week 1: parse → chunk → embed → store pipeline.
Week 2: retrieval (RRF), rerank (Cohere), extraction (12 CUAD categories), risk flags.
Week 3: QA endpoint with citation grounding, eval harness + JSONL store, evals API, Next.js frontend.

### What's built and working

| Module | Location | Status |
|--------|----------|--------|
| Config | `backend/app/config.py` | ✅ pydantic-settings, all env vars + `evals_results_dir` |
| DB models | `backend/app/db/models.py` | ✅ Contract, Chunk (pgvector + JSONB bbox) |
| DB session | `backend/app/db/session.py` | ✅ SQLAlchemy async, asyncpg |
| Migration | `backend/migrations/versions/0001_initial_schema.py` | ✅ tables + ivfflat + bm25 indexes |
| Parsing | `backend/app/parsing/__init__.py` | ✅ PyMuPDF block extraction + bbox |
| Chunking | `backend/app/chunking/__init__.py` | ✅ dual granularity (section 1500t, clause 300t) |
| Embeddings | `backend/app/embeddings/__init__.py` | ✅ Voyage AI, batched, tenacity retry |
| LLM client | `backend/app/llm/__init__.py` | ✅ Anthropic, Tier enum, tenacity retry |
| Observability | `backend/app/observability/__init__.py` | ✅ Langfuse wrapper, disabled gracefully if keys absent |
| Contracts API | `backend/app/api/contracts.py` | ✅ POST /upload, GET /, GET /{id} |
| App startup | `backend/app/main.py` | ✅ lifespan wires all clients, flushes on shutdown |
| Retrieval | `backend/app/retrieval/__init__.py` | ✅ pgvector dense + pg_search BM25 + RRF k=60 |
| Rerank | `backend/app/rerank/__init__.py` | ✅ Cohere rerank-3, top-8, tenacity retry |
| Extraction | `backend/app/extraction/__init__.py` | ✅ 12 CUAD categories, Haiku pass + Sonnet recheck |
| Flags | `backend/app/flags/__init__.py` | ✅ 4 risk flags, deterministic (regex + extraction) |
| Citations | `backend/app/citations/__init__.py` | ✅ grounding validation, containment metrics, bbox IoU |
| QA API | `backend/app/api/qa.py` | ✅ POST /ask — retrieve→rerank→Sonnet→grounding validate |
| Evals module | `backend/app/evals/__init__.py` | ✅ recall@k + MRR@k via content-containment |
| Evals store | `backend/app/evals/store.py` | ✅ EvalResultEntry dataclass, JSONL save/load |
| Evals API | `backend/app/api/evals.py` | ✅ GET /summary, GET /failures (paginated, bucket filter) |
| Golden set | `evals/golden/sample.jsonl` | ✅ 9 questions — 3 per bucket (A/B/C); set contract_id after indexing |
| Eval runner | `evals/scripts/run_eval.py` | ✅ async script, imports app directly, writes JSONL results |
| Frontend | `frontend/` | ✅ Next.js 16 + TanStack Query + Recharts + shadcn/ui |

### What's still a stub (raises NotImplementedError)

- `app/api/qa.py` → `/evals/experiments` — Week 4
- `app/api/deviation.py` — Week 5–6
- `app/playbooks/` — Week 4
- `app/deviation/` — Week 5
- `frontend/src/components/evals/TabExperiments.tsx` — Week 4

### Frontend routes

| Route | What it does |
|-------|-------------|
| `/` | Landing page — links to evals dashboard and API docs |
| `/evals` | 4-tab dashboard: Metrics, Failures, Experiments (stub), Live Demo |

### Running the eval harness

```bash
# 1. Index a contract first via POST /api/contracts/upload
# 2. Update contract_id in evals/golden/sample.jsonl
# 3. Run:
cd backend
uv run python ../evals/scripts/run_eval.py
# Results written to evals/results/run_<timestamp>.jsonl
```

---

## How to run locally

### Prerequisites
- Docker Desktop with WSL integration enabled
- `uv` installed (`curl -LsSf https://astral.sh/uv | sh`)
- Real API keys in `.env` (copy from `.env.example`, fill in values)

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

API docs at http://localhost:8000/docs  
Health check: `curl http://localhost:8000/health`

### Run linter / type checker
```bash
cd backend
uv run ruff check .
uv run mypy app
```

---

## Key non-obvious constraints

### pg_search query syntax (Spike 5)
The `@@@` operator requires **field-qualified terms**: `'content:term'` not `'term'`.
Plain unqualified terms produce a parse error. This applies in the Week 2 retrieval module.
Multi-word: `'content:foo OR content:bar'` or `paradedb.parse()`.

### pgvector + SQLAlchemy async (asyncpg)
Do NOT call `register_vector()` from pgvector.asyncpg — it's for raw asyncpg connections only.
The `pgvector.sqlalchemy.Vector` type handles encoding at the SQLAlchemy layer. Just use the type.

### Chunking dual granularity
`chunk_blocks()` returns both section chunks (~1500 tokens) and clause chunks (~300 tokens) for the same
document. Only clause chunks get embeddings — they are the QA retrieval unit. Section chunks
are stored with `embedding=None` for the Week 5 deviation pipeline.

### Citation metric (Spike 1)
Primary: **containment** — cited chunk text contains the gold character span as a substring.
Secondary/visual: set-union IoU@0.5 (not CI-gated). The golden set schema uses `gold_spans`
(character offsets), not bboxes, as the primary ground truth.

### Model IDs — do not change
- Haiku: `claude-haiku-4-5-20251001` (high-volume, classification, extraction)
- Sonnet: `claude-sonnet-4-6` (QA, deviation summaries, accuracy-critical)
- Embeddings: `voyage-3-large` (1024-dim); alt `voyage-law-2` via `VOYAGE_MODEL` env var

### Langfuse optional
`langfuse_public_key` and `langfuse_secret_key` are `str | None` in Settings. If absent,
the ObservabilityClient logs a warning and all `.trace()` calls are no-ops. The app starts fine
without them.

### Alembic — run from backend/
`alembic.ini` is at `backend/alembic.ini`. Always run `alembic` from `backend/`:
```bash
cd backend && uv run alembic upgrade head
```

---

## Architecture decisions (see docs/decision-log.md for full ADRs)

- **Single Postgres** (ParadeDB) for vectors + BM25 + relational — no separate vector DB
- **RRF k=60** fusing top-20 dense + top-20 sparse results — validated in Spike 5
- **LangGraph** scoped only to the deviation pipeline (5-node graph) — NOT used for QA
- **PyMuPDF** (not LlamaParse) as primary parser — bboxes needed for citation containment
- **Cohere rerank-3** — Week 2, after fused retrieval, top-8 passed to LLM

---

## 12 CUAD extraction categories (Spike 3)

Governing Law, Renewal Term, Notice Period to Terminate Renewal, Termination for Convenience,
Indemnification, Confidentiality, Anti-Assignment, Non-Compete, Cap on Liability,
Change of Control, IP Ownership Assignment, Uncapped Liability.
Baseline: CUAD paper RoBERTa-large F1 (see `docs/spikes/spike-3-contracteval-overlap.md`).

---

## Week sequence

| Week | Focus |
|------|-------|
| W1 | ✅ parsing, chunking, DB, LLM client, Langfuse, contracts API |
| W2 | ✅ retrieval (RRF query), rerank (Cohere), extraction (12 categories), risk flags |
| W3 | ✅ QA endpoint, citations, eval harness, eval frontend |
| W4 | playbook YAML loader, experiment tracking |
| W5 | LangGraph deviation pipeline (5-node) |
| W6 | HITL interrupt, eval CI gate (`mean − 1·stddev`) |
