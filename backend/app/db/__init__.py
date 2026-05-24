"""
Database layer. SQLAlchemy 2.x with async sessions (asyncpg driver). Contains:
  - `models.py` — ORM models for Contract, Chunk, EvalRun, EvalResult, DeviationRun
  - `session.py` — async engine factory and `get_session()` dependency
  - Alembic integration via `migrations/` (env.py points at these models)

ParadeDB (Postgres + pgvector + pg_search) is the only database. The pgvector
extension stores chunk embeddings; pg_search provides BM25 indexing. Both
extensions must be present — see `docker/README.md` and Spike 5 for verification.

Implemented: Week 1 (models + session), migrations added as schema evolves.
"""
