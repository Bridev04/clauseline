# CI Workflows

## Current: `ci.yml`

Runs on every push and PR: ruff lint, mypy type check, pytest (unit tests only). Fast — no services required. Integration tests (requiring Postgres) are excluded via pytest markers and will be added to CI when the DB layer is implemented in Week 1.

## Planned: eval gate (Week 6)

The eval gate will be a separate workflow (or a second job in `ci.yml`) that:

1. Spins up a ParadeDB Postgres service container
2. Loads the baseline model and golden contract set from `evals/golden/`
3. Runs `uv run python evals/scripts/run_eval.py --golden evals/golden/ --output /tmp/run.json`
4. For each deterministic metric (recall@8, MRR@8, citation IoU, refusal accuracy): fails the PR if the value regresses vs. `evals/results/baseline.json`
5. For each LLM-judge metric (Ragas faithfulness, answer relevance): runs the eval 3 times, computes `mean − 1·stddev`, and fails the PR if the adjusted score drops below the baseline

The baseline JSON (`evals/results/baseline.json`) is committed to the repo and updated manually when a deliberate improvement is confirmed. A PR that improves metrics should update the baseline as part of the same commit.

The eval gate is intentionally not gating on the LLM-judge metrics alone (high variance) but on the adjusted score, which is more stable across runs.
