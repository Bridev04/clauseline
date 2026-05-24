# Architecture

See the one-screen diagram in the root [README.md](../README.md). This document adds the reasoning behind each layer choice.

---

## Layer-by-layer rationale

### Parsing: PyMuPDF4LLM over Unstructured

PyMuPDF4LLM returns markdown text **and** bounding-box coordinates for every block in the PDF. Bounding boxes are non-negotiable for the citation IoU metric — without them, "cited evidence" is just chunk text with no verifiable spatial link to the source document. Unstructured.io was considered but does not expose bbox data in a form that survives its chunking pipeline. LlamaParse (LlamaCloud) is retained as a fallback specifically for scanned PDFs and complex multi-column layouts where PyMuPDF's layout detection degrades; it costs money per page, so it is invoked only when the primary parser fails a confidence check.

### Chunking: Dual granularity, layout-aware

Two chunk sizes serve different consumers: section-level chunks (~1500 tokens) give the deviation pipeline enough context to reason about entire clauses and their surrounding intent; clause-level chunks (~300 tokens) are the retrieval unit for QA, where precision matters more than context breadth. Both granularities store the union of their constituent block bboxes. A clause that straddles a section boundary appears in both section chunks — intentional redundancy to avoid missing evidence at boundaries.

### Database: ParadeDB over Supabase + Python BM25

ParadeDB gives us pgvector cosine search and pg_search BM25 in a single Postgres container. The critical advantage is that both indexes can be queried in **one SQL CTE with RRF fusion** — no Python-side merging, no second round-trip. Supabase was considered but adds managed-service overhead and would still require a separate BM25 implementation (e.g., rank_bm25) in Python, which breaks the single-query constraint. A plain Postgres + `tsvector` fallback is documented in Spike 5 in case pg_search syntax is incompatible.

### Embeddings: Voyage over OpenAI

`voyage-3-large` consistently outperforms `text-embedding-3-large` on legal domain benchmarks. The domain-specific `voyage-law-2` is available as a configuration swap (no code change, just `VOYAGE_MODEL=voyage-law-2`). OpenAI embeddings are not wired because switching embedding models requires re-indexing all chunks — the model is a load-bearing choice that should be validated early (Spike 3 informs this indirectly via ContractEval category overlap).

### Reranker: Cohere rerank-3 over local cross-encoder

A local cross-encoder (e.g., `cross-encoder/ms-marco-MiniLM`) would eliminate the Cohere API dependency but adds GPU/CPU latency variability in a portfolio context where p95 latency is a headline metric. Cohere rerank-3 is state-of-the-art on BEIR and offers a clean API. If cost becomes a concern at scale, the local cross-encoder swap is a single-module change in `app/rerank/`.

### LLM tier routing: Haiku for volume, Sonnet for precision

The system makes many LLM calls per query (extraction, classification, QA answer, citation verification, deviation comparison). Routing all calls through Sonnet would make every query expensive. Haiku handles the high-volume, lower-stakes passes (parallel extraction, classification, initial comparisons); Sonnet handles the low-volume, high-stakes passes (final QA answer, deviation summaries, edge-case re-checks). The routing logic lives entirely in `app/llm/` so it can be tuned without touching business logic.

### Agentic scope: LangGraph for deviation only

LangGraph adds coordination overhead that is only justified where a workflow has non-trivial fan-out and a human-in-the-loop interrupt. The deviation pipeline qualifies (parallel classification, parallel comparison, HITL before commit). QA does not — it is a linear pipeline with no branching that warrants a graph. Adding LangGraph to QA would be complexity theater.

### Observability: Langfuse

Every LLM call is traced in Langfuse. The eval failure explorer (Tab 2 of `/evals`) embeds Langfuse trace links so any failure can be inspected token-by-token without context-switching. This is the most direct link between the eval system and the observability system — it is why Langfuse was chosen over a generic logging solution.
