"""
Hybrid retrieval via a single Postgres query. Combines pgvector cosine similarity
(`<=>` operator) and pg_search BM25 (`@@@` operator) using Reciprocal Rank Fusion
with k=60. Top-20 dense candidates and top-20 sparse candidates are fused in one
SQL CTE, avoiding a round-trip. The fused list is passed to the rerank layer.

Spike 5 confirmed (2026-05-24): pg_search 0.23.4 + vector 0.8.1 on ParadeDB latest.
Non-obvious syntax constraint: the `@@@` operator requires field-qualified queries
(`'content:term'`), not bare terms (`'term'`). Use `paradedb.parse()` for phrases.

Implemented: Week 2.
"""
