# Spike 4 — README Outline

**Status:** ✅ DONE

---

## Goal

Force clarity on what the system claims before any code is written. If you can't write a placeholder README with real metric names and a real architecture diagram, you don't yet know what you're building.

---

## Deliverable

[`README.md`](../../README.md) — the root README satisfies this spike. It contains:
- Headline results table with named metrics (TBD values — filled after eval runs)
- One-screen architecture diagram covering the full pipeline
- The four load-bearing pieces explicitly named
- Eval strategy table with metric names, methods, and gate conditions
- All tech stack decisions documented

---

## Note

Any future change to "what the system claims" — new metrics, changed architecture, different models — should be made in the README **first**, then implemented. The README is the contract between the builder and the portfolio reader.
