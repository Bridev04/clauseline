# Clauseline — Project CLAUDE.md

## What this is

Contract intelligence portfolio project: hybrid retrieval (pgvector + pg_search BM25 + RRF),
QA with citations, and a deviation-detection pipeline. Frontend scaffolded in Week 3.

---

## Current state

**Phase: Week 8 complete** (as of 2026-05-26)

All 5 pre-Week-1 validation spikes are done (see `docs/spikes/`).
Week 1: parse → chunk → embed → store pipeline.
Week 2: retrieval (RRF), rerank (Cohere), extraction (12 CUAD categories), risk flags.
Week 3: QA endpoint with citation grounding, eval harness + JSONL store, evals API, Next.js frontend.
Week 4: playbook YAML loader (Pydantic v2 schema), /evals/experiments endpoint, TabExperiments frontend.
Week 5: LangGraph deviation pipeline (5-node), deviation_runs DB table + migration, POST /deviation/run + GET /deviation/runs/{id}.
Week 6: HITL interrupt (6th LangGraph node + MemorySaver + Command resume), POST /deviation/{id}/review, GET /deviation/runs list, eval CI gate script + GET /evals/ci-gate, TabDeviation frontend (5th tab with inline review panel).
Week 7: AsyncPostgresSaver (durable deviation checkpoints), GET /api/playbooks/, upload + deviation-launch UI in frontend, eval CI gate wired into GitHub Actions, CORS from settings.
Week 8: golden set aligned to indexed contract, whitespace-normalized grounding fix in citations/evals modules, Voyage rate-limit handling in eval runner, README populated with real metrics (run 2026-05-26T075710).

### What's built and working

| Module | Location | Status |
|--------|----------|--------|
| Config | `backend/app/config.py` | ✅ pydantic-settings, all env vars + `evals_results_dir`, `playbooks_dir` |
| DB models | `backend/app/db/models.py` | ✅ Contract, Chunk, DeviationRun (pgvector + JSONB) |
| DB session | `backend/app/db/session.py` | ✅ SQLAlchemy async, asyncpg |
| Migration | `backend/migrations/versions/0001_initial_schema.py` | ✅ tables + ivfflat + bm25 indexes |
| Migration | `backend/migrations/versions/0002_deviation_runs.py` | ✅ deviation_runs table + indexes |
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
| Evals API | `backend/app/api/evals.py` | ✅ GET /summary, GET /failures, GET /experiments (run timeline + deltas) |
| Golden set | `evals/golden/sample.jsonl` | ✅ 9 questions — 3 per bucket (A/B/C); set contract_id after indexing |
| Eval runner | `evals/scripts/run_eval.py` | ✅ async script, imports app directly, writes JSONL results |
| Playbooks | `backend/app/playbooks/__init__.py` | ✅ Pydantic v2 schema, YAML loader, CUADCategory/Severity/Condition enums |
| Playbook YAMLs | `data/playbooks/yaml/`, `evals/playbooks/yaml/` | ✅ prod sample + eval fixture |
| Frontend | `frontend/` | ✅ Next.js 16 + TanStack Query + Recharts + shadcn/ui |
| TabExperiments | `frontend/src/components/evals/TabExperiments.tsx` | ✅ line chart + run table with deltas |
| Deviation pipeline | `backend/app/deviation/__init__.py` | ✅ 6-node LangGraph: Loader→Classifier→Comparator→Scorer→Summarizer→HITL Reviewer |
| Deviation API | `backend/app/api/deviation.py` | ✅ POST /run (pauses at HITL), GET /runs, GET /runs/{id}, POST /{id}/review |
| Eval CI gate | `evals/scripts/ci_gate.py` | ✅ standalone script, mean − 1·stddev, exit 0/1 |
| Evals API | `backend/app/api/evals.py` | ✅ GET /summary, /failures, /experiments, /ci-gate |
| Migration | `backend/migrations/versions/0003_hitl_review.py` | ✅ awaiting_review enum value + review_decision/notes/reviewed_at columns |
| TabDeviation | `frontend/src/components/evals/TabDeviation.tsx` | ✅ runs table + inline HITL review panel (Approve/Reject) |
| Deviation checkpointer | `backend/app/deviation/__init__.py` | ✅ AsyncPostgresSaver (durable, injected via lifespan) |
| Playbooks API | `backend/app/api/playbooks.py` | ✅ GET /api/playbooks/ — metadata list |
| Upload UI | `frontend/src/components/UploadContract.tsx` | ✅ PDF upload card, invalidates contracts query |
| Deviation launcher | `frontend/src/components/DeviationLauncher.tsx` | ✅ contract + playbook picker, starts deviation run |

### What's still a stub

Nothing — all endpoints are implemented.

### Frontend routes

| Route | What it does |
|-------|-------------|
| `/` | Landing page — links to evals dashboard and API docs |
| `/evals` | 5-tab dashboard: Metrics, Failures, Experiments, Live Demo, Deviation |

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
uv run mypy app          # 0 errors expected

cd ../frontend
npx tsc --noEmit         # 0 errors expected
npm run build            # next build must compile cleanly
```

All four checks are expected to pass with 0 errors/warnings as of Week 7.

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
- **LangGraph** scoped only to the deviation pipeline (6-node graph with HITL interrupt) — NOT used for QA. `AsyncPostgresSaver` (Week 7) persists checkpoints in `checkpoint_*` tables; injected via `app.state` at lifespan startup.
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
| W4 | ✅ playbook YAML loader, experiment tracking |
| W5 | ✅ LangGraph deviation pipeline (5-node), deviation_runs table, POST /deviation/run |
| W6 | ✅ HITL interrupt (6th node + MemorySaver), POST /review, eval CI gate script + API endpoint, TabDeviation UI |
| W7 | ✅ AsyncPostgresSaver (durable checkpoints), GET /api/playbooks/, upload + deviation-launch UI, CI gate in Actions |
| W8 | ✅ golden set aligned to real contract, grounding whitespace-norm fix, eval rate-limit handling, README metrics populated |
