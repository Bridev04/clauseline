# Decision Log

ADR-lite format. One entry per architectural decision. Each entry: **Decision / Context / Alternatives considered / Why this one / Reversibility**.

---

## 001 — Monorepo

**Decision:** Single repository containing backend, frontend, evals, data, docs, and CI.

**Context:** The backend, evals, and frontend share schema types, the golden set lives alongside the code that consumes it, and CI needs to run evals against the backend in the same checkout.

**Alternatives considered:** Separate repos for backend and frontend (common at scale). Separate `evals` repo.

**Why this one:** At portfolio scale, cross-repo coordination adds friction with no benefit. The eval gate in CI requires the backend and golden set to be in the same repo anyway. A single `pyproject.toml` in `backend/` keeps the Python environment coherent.

**Reversibility:** Medium. Splitting later requires migrating CI, updating import paths, and deciding where the golden set lives. Doable but annoying.

---

## 002 — FastAPI + Python 3.11

**Decision:** FastAPI as the web framework, Python 3.11 as the runtime.

**Context:** All ML/LLM/data libraries are Python-native. The pipeline is async I/O-bound (Postgres queries, API calls). FastAPI provides native async support, Pydantic v2 validation, and automatic OpenAPI docs.

**Alternatives considered:** Django (too heavyweight, ORM-centric), Flask (no native async), Express/Node (poor ML library ecosystem for this use case).

**Why this one:** FastAPI + Pydantic v2 is the de facto standard for Python ML services in 2026. The automatic `/docs` page is useful for the portfolio. Pydantic v2 is already required for pydantic-settings.

**Reversibility:** High. FastAPI is thin; business logic in `app/` modules is framework-agnostic.

---

## 003 — uv as package manager

**Decision:** `uv` for dependency resolution, virtual environments, and script running.

**Context:** `pip` + `venv` is slow and produces non-reproducible installs without a lockfile. Poetry is slower than uv. uv resolves and installs in seconds and produces a `uv.lock` that pins the full dependency tree.

**Alternatives considered:** Poetry (mature but slow), pip-compile (two-step, more friction), conda (wrong ecosystem for this project).

**Why this one:** uv is the fastest Python package manager available in 2026 and integrates cleanly with `pyproject.toml`. CI uses `astral-sh/setup-uv` for a one-step install.

**Reversibility:** High. `pyproject.toml` is standard; migrating to Poetry or pip-compile is a tooling change, not a code change.

---

## 004 — ParadeDB (not Supabase, not Postgres + Python BM25)

**Decision:** `paradedb/paradedb` Docker image for Postgres + pgvector + pg_search.

**Context:** The retrieval strategy requires BM25 and dense vector search fused via RRF in a single SQL query. This is only possible if both indexes are in the same database engine.

**Alternatives considered:**
- Supabase: managed Postgres with pgvector, but no native BM25 — would require Python-side BM25 (rank_bm25) and a second round-trip for fusion.
- Plain Postgres + `tsvector`: built-in full-text search, but not true BM25 (no IDF term weighting tuned for retrieval). Documented as the Spike 5 fallback.
- Elasticsearch: true BM25 but a separate service, separate query language, and no pgvector.

**Why this one:** ParadeDB bundles both indexes in one container with a unified SQL interface. A single CTE with `<=>` and `@@@` operators produces fused results without Python coordination. This is the key architectural bet — verified in Spike 5.

**Reversibility:** Medium-low. Switching away requires re-indexing all chunks and rewriting the retrieval query. The fallback (`tsvector`) is documented and the retrieval module is isolated.

---

## 005 — Voyage embeddings (not OpenAI)

**Decision:** `voyage-3-large` as default embedding model, `voyage-law-2` as domain-specific alt.

**Context:** Embeddings are the first filter before retrieval. Legal text has domain-specific vocabulary (indemnification, governing law, force majeure) that general embeddings handle less precisely.

**Alternatives considered:** `text-embedding-3-large` (OpenAI) — strong general-purpose; `ada-002` — deprecated; local `bge-large-en` — adds GPU dependency.

**Why this one:** Voyage consistently outperforms OpenAI embeddings on legal domain benchmarks. The model swap is a one-line env var change — the embedding client is abstracted in `app/embeddings/`. The legal-specific `voyage-law-2` is available as a configuration experiment without code changes.

**Reversibility:** High for the abstraction; Medium for the data — changing embedding models requires re-indexing all stored chunks.

---

## 006 — Cohere rerank-3 (not local cross-encoder)

**Decision:** Cohere `rerank-3` API for the reranking step.

**Context:** Reranking is the last filter before the LLM sees context. Quality here directly affects faithfulness. A cross-encoder is more accurate than bi-encoder retrieval but adds latency.

**Alternatives considered:** `cross-encoder/ms-marco-MiniLM-L-12-v2` (local) — eliminates API cost but adds GPU/CPU latency variability. BGE reranker — open-source, similar tradeoff.

**Why this one:** Cohere rerank-3 is state-of-the-art on BEIR. In a portfolio context where p95 latency is a headline metric, API-based reranking has more predictable tail latency than a local model under load. The reranker is isolated in `app/rerank/` — swapping to a local model is a single-module change.

**Reversibility:** High. One module swap, no schema changes.

---

## 007 — Haiku/Sonnet tier routing

**Decision:** Claude Haiku 4.5 for high-volume/lower-stakes calls; Claude Sonnet 4.6 for precision/high-stakes calls.

**Context:** A single query may trigger multiple LLM calls: extraction (12 categories), classification (N rules), QA answer, citation check, deviation summary. All-Sonnet would be 5–10× more expensive per query.

**Alternatives considered:** Single model (all Haiku — cheap but imprecise for QA), single model (all Sonnet — expensive), GPT-4o (non-Anthropic, breaks vendor consolidation).

**Why this one:** Haiku handles the parallel, high-volume passes where a wrong label on one category can be caught downstream. Sonnet handles the single-pass, user-visible outputs where a bad answer is a hard failure. Routing logic lives entirely in `app/llm/` behind a `Tier` enum.

**Reversibility:** High. Change the routing rule in one place; all callers use the enum.

---

## 008 — LangGraph scoped to deviation pipeline only

**Decision:** LangGraph is used only for the 5-node deviation pipeline. QA and extraction use linear async Python.

**Context:** LangGraph adds graph coordination, state management, and HITL interrupt machinery. This is valuable when a workflow has non-trivial fan-out and a human gate. It adds complexity when a workflow is linear.

**Alternatives considered:** LangGraph for all pipelines — over-engineered for QA. Plain Python coroutines for deviation — doable but HITL interrupt is harder to implement correctly without a state graph.

**Why this one:** The deviation pipeline has genuine fan-out (parallel Classifier, parallel Comparator) and a required HITL interrupt before committing results. QA is: retrieve → rerank → generate → validate. No graph needed.

**Reversibility:** High. The deviation pipeline is self-contained in `app/deviation/`.

---

## 009 — AsyncPostgresSaver for deviation checkpoints

**Decision:** Replace the `MemorySaver` singleton with `AsyncPostgresSaver` (from `langgraph-checkpoint-postgres`) so deviation pipeline checkpoints survive server restarts.

**Context:** `MemorySaver` was used through Week 6 as a known production gap — checkpoints lived only in-process. Any server restart between `POST /deviation/run` (HITL interrupt) and `POST /deviation/{id}/review` would lose the checkpoint, making the review endpoint raise `DeviationRunError`. With `AsyncPostgresSaver`, checkpoints persist in Postgres under `checkpoint_*` tables (managed by the saver's `setup()` method).

**Tables created by `AsyncPostgresSaver.setup()` (idempotent):**
- `checkpoint_migrations` — migration version tracking
- `checkpoints` — one row per (thread_id, checkpoint_ns, checkpoint_id)
- `checkpoint_blobs` — node output blobs
- `checkpoint_writes` — pending write entries

None of these names conflict with our tables (`contracts`, `chunks`, `deviation_runs`).

**DSN:** The saver requires a standard `postgresql://` URL (psycopg v3 driver). We derive it by stripping the `+asyncpg` SQLAlchemy driver suffix from `database_url` at lifespan startup. This avoids adding a second env var for what is effectively the same connection.

**Connection management:** `AsyncPostgresSaver.from_conn_string` is an async context manager that opens a single psycopg connection and closes it on exit. For this portfolio's traffic profile, a single connection is sufficient. A production deployment would swap this for a pool (psycopg_pool) or `AsyncPostgresSaver(conn=pool_conn)`.

**Limitations:** Only runs that have already committed a checkpoint (i.e., reached the HITL interrupt) can be resumed after a restart. A run that crashes mid-pipeline is still lost — no crash recovery is promised.

**Alternatives considered:** Keep `MemorySaver` and document the limitation — viable at portfolio scale but embarrassing as the only documented production gap. Use `AsyncPostgresSaver` with a dedicated pool — more correct, but over-engineered for current load; extractable later.

**Why this one:** Closes the only documented production gap (`MemorySaver` loses runs on restart) with a single context manager in `lifespan`. The checkpointer is now passed through the call stack (`run_deviation_pipeline`, `resume_deviation_pipeline`) rather than held as a module-level singleton — easier to test and swap.

**Reversibility:** Medium. Swap `AsyncPostgresSaver.from_conn_string(...)` back to `MemorySaver()` in `main.py` and update the two function signatures. The `checkpoint_*` tables remain in Postgres but are inert.
