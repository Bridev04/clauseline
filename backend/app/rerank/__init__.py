"""
Cohere rerank-3 wrapper. Takes the fused RRF candidate list (~40 chunks) and
returns the top-K (default 8) reranked by semantic relevance to the query.
Reranking is the last filtering stage before the LLM sees context — it directly
affects faithfulness. A local cross-encoder was considered but rejected in favor
of the Cohere API (see docs/decision-log.md: "Cohere rerank vs local cross-encoder").

Implemented: Week 2.
"""
