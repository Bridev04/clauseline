"""
Voyage AI embedding client wrapper. Default model is `voyage-3-large`; the
legal-domain fine-tuned `voyage-law-2` is available as an alt via the VOYAGE_MODEL
env var. Exposes a single async `embed(texts)` function that handles batching
and rate-limit retries (via tenacity). Embeddings are 1024-dimensional floats
stored in pgvector's `vector` column type.

Implemented: Week 1.
"""
