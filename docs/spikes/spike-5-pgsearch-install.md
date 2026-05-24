# Spike 5 — pg_search Install Verification

**Status:** ✅ DONE

---

## Goal

Verify that the ParadeDB Docker image supports the exact SQL syntax needed for the hybrid RRF retrieval query — specifically that `pgvector` (`<=>`) and `pg_search` BM25 (`@@@`) can be combined in a single SQL CTE with RRF fusion. This must be validated before any retrieval code is written.

---

## Method

1. Bring up the ParadeDB container: `docker compose -f docker/docker-compose.yml up -d`
2. Connect and install extensions:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_search;
   SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_search');
   ```
3. Create a minimal test table with 5 dummy chunks:
   ```sql
   CREATE TABLE test_chunks (
     id SERIAL PRIMARY KEY,
     content TEXT,
     embedding vector(1024)
   );
   -- Insert 5 rows with fake embeddings and text
   INSERT INTO test_chunks (content, embedding) VALUES
     ('The governing law shall be California.', '[0.1, 0.2, ...]'),
     ...;
   ```
4. Create the BM25 index:
   ```sql
   CREATE INDEX test_chunks_bm25 ON test_chunks
   USING bm25 (id, content) WITH (key_field='id');
   ```
5. Run the fused query:
   ```sql
   WITH dense AS (
     SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector) AS rank
     FROM test_chunks
     ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
     LIMIT 5
   ),
   sparse AS (
     SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
     FROM test_chunks, paradedb.score(id) AS score
     WHERE test_chunks @@@ 'governing law'
     LIMIT 5
   ),
   rrf AS (
     SELECT id, SUM(1.0 / (60 + rank)) AS rrf_score
     FROM (SELECT id, rank FROM dense UNION ALL SELECT id, rank FROM sparse) sub
     GROUP BY id
   )
   SELECT tc.id, tc.content, rrf.rrf_score
   FROM rrf JOIN test_chunks tc ON tc.id = rrf.id
   ORDER BY rrf_score DESC;
   ```
6. Confirm: query executes without error and returns rows ordered by RRF score.

---

## Decision rule

| Outcome | Decision |
|---------|----------|
| Extensions install and fused query runs correctly | pg_search + pgvector + RRF is validated. Proceed with retrieval module implementation. Update `docker/README.md` with verified syntax. |
| Extensions install but pg_search query syntax differs from expected | Adjust to the correct pg_search API (it may use a different function name or operator). Document the correct syntax. Proceed if the semantics are equivalent. |
| `pg_search` extension is not available in the paradedb image | Fall back to `tsvector` + `ts_rank_cd` for sparse retrieval. This is true BM25 → BM25-approximate. Update the README to say "BM25-approximate" not "BM25". File an issue. |
| `pgvector` is not available | Highly unlikely given ParadeDB's documented feature set. If it happens, switch to a plain Postgres image + manual pgvector extension install. |

---

## Findings

**Date:** 2026-05-24. Docker Desktop 29.4.2 / Compose 5.1.3 on WSL2.

### Extension versions confirmed

```
 extname  | extversion
-----------+------------
 pg_search | 0.23.4
 vector    | 0.8.1
```

Both extensions are pre-installed in `paradedb/paradedb:latest`. No manual `CREATE EXTENSION` needed at deploy time (the image already loads them), but the commands are idempotent and safe to run.

### Volume mount correction

The compose file originally used a bind mount at `/var/lib/postgresql/data`. Postgres 18+ (the base used by ParadeDB) expects the mount at `/var/lib/postgresql` (the parent). Fixed to use a Docker named volume (`paradedb_data`) mounting at `/var/lib/postgresql`.

### pg_search query syntax (key finding)

The `@@@` operator requires **field-qualified queries**: `'content:term'` not `'term'`. Plain unqualified terms produce `ERROR: could not parse query string 'id:(term)'`. The correct syntax:

```sql
-- ✅ correct
WHERE table_name @@@ 'content:governing'

-- ❌ wrong — produces parse error
WHERE table_name @@@ 'governing'
```

### Fused RRF query — confirmed working

Full CTE with 5 dummy chunks, vector query against `[0.9,0.1,0.1,0.1]`, BM25 query for `content:governing`, k=60:

```
 id | rrf_score |                                      content
----+-----------+------------------------------------------------------------------------------------
  1 |  0.032787 | The governing law shall be the laws of the State of California.
  5 |  0.016129 | All confidential information shall be kept secret for five years after disclosure.
  2 |  0.015873 | Neither party may assign this Agreement without prior written consent.
  3 |  0.015625 | Liability of either party shall not exceed fees paid in the prior twelve months.
  4 |  0.015385 | This Agreement shall automatically renew for one-year terms unless terminated.
```

Row 1 (governing law) scores `0.032787` = 1/(60+1) + 1/(60+1) — ranked #1 in both dense and sparse, receiving double RRF contribution. Rows 2–5 appear only in the dense ranking. Ordering is exactly correct.

### Confirmed working SQL pattern

```sql
WITH dense AS (
  SELECT id,
         ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank
  FROM chunks
  ORDER BY embedding <=> $1::vector
  LIMIT 20
),
sparse AS (
  SELECT id,
         ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS rank
  FROM chunks
  WHERE chunks @@@ 'content:' || $2   -- field-qualified term
  LIMIT 20
),
rrf AS (
  SELECT id,
         SUM(1.0 / (60.0 + rank)) AS rrf_score
  FROM (
    SELECT id, rank FROM dense
    UNION ALL
    SELECT id, rank FROM sparse
  ) sub
  GROUP BY id
)
SELECT c.*, rrf.rrf_score
FROM rrf JOIN chunks c ON c.id = rrf.id
ORDER BY rrf_score DESC
LIMIT 8;  -- RERANK_TOP_K after this
```

For multi-term queries use `paradedb.parse()` or concatenate field-qualified terms with `OR`:
`'content:governing OR content:law'`

---

## Decision

**Proceed with the fused pgvector + pg_search + RRF retrieval architecture as designed.** No fallback to `tsvector` needed.

**One syntax change required in `app/retrieval/`:** BM25 queries must use `field:term` format. Multi-word queries should use `paradedb.parse()` for phrase matching or space-separated field:term pairs for OR behavior. Document this in the retrieval module as a non-obvious constraint.

**Files to update:**
- `app/retrieval/__init__.py` — add note that pg_search requires `content:term` syntax (not bare terms); update when implementing Week 2
- `docker/README.md` — update verification commands with correct syntax and confirmed version numbers
- `docker/docker-compose.yml` — already updated: named volume `paradedb_data`, mount at `/var/lib/postgresql`
