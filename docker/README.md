# Docker

## Starting Postgres (ParadeDB)

```bash
# From the repo root — copy .env.example to .env first
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d
```

The ParadeDB image bundles pgvector and pg_search (BM25) in a single Postgres container. No separate extension installs required — but **Spike 5 verifies this end-to-end before any retrieval code is written.**

## Verifying extensions are available

```bash
docker exec docker-postgres-1 psql -U clauseline -d clauseline -c "
  SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_search') ORDER BY extname;
"
```

Expected output (confirmed 2026-05-24):
```
  extname  | extversion
-----------+------------
 pg_search | 0.23.4
 vector    | 0.8.1
```

Both extensions are pre-installed in the ParadeDB image — no manual install needed.

## Verified RRF query syntax (Spike 5 ✅)

The fused query is confirmed working. Key syntax points:
- pgvector: `embedding <=> '[...]'::vector` (cosine distance, lower = more similar)
- pg_search: `table_name @@@ 'content:term'` — **field-qualified terms required**; bare terms produce a parse error
- Multi-word: use `'content:term1 OR content:term2'` or `paradedb.parse()`
- RRF: CTE unions both ranked lists and computes `SUM(1.0 / (60.0 + rank))`

See `docs/spikes/spike-5-pgsearch-install.md` for the full working query.

## Connecting

```
Host:     localhost
Port:     5432 (or POSTGRES_PORT from .env)
Database: clauseline
User:     clauseline
Password: clauseline
```

## Langfuse (optional self-hosted)

The default observability setup uses Langfuse cloud — just set `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and leave `LANGFUSE_HOST=https://cloud.langfuse.com` in `.env`.

To run Langfuse locally, uncomment the Langfuse service block in `docker-compose.yml`
and follow the [Langfuse self-host guide](https://langfuse.com/docs/deployment/self-host).
