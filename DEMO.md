# Clauseline — Demo Mode (offline, interview-ready)

This is the **bulletproof way to show Clauseline live** — in an interview, on a
plane, or anywhere you don't want to depend on Docker, ParadeDB, or three paid
API keys holding up under pressure.

Demo mode runs a **zero-dependency stand-in backend** ([`backend/demo_server.py`](backend/demo_server.py))
that speaks the exact same HTTP API as the real FastAPI service, plus the real
Next.js dashboard. No Docker. No API keys. No network calls.

The eval-dashboard numbers are aggregated from the project's **real** eval run
files (`evals/results/*.jsonl`); the QA answers are curated from the real golden
set. The production pipeline (hybrid retrieval, LangGraph deviation graph,
citation grounding) still lives in `backend/app/` — demo mode just swaps the
runtime so it's always demonstrable.

---

## One command

**Windows (PowerShell):**
```powershell
.\demo.ps1
```

**macOS / Linux / Git Bash:**
```bash
./demo.sh
```

The launcher starts the demo backend on `:8000`, installs the frontend deps on
first run, and starts the dashboard on `:3000`. When it prints **Ready**, open:

**http://localhost:3000/evals**

Press `Ctrl+C` to stop everything.

> First run downloads frontend dependencies (~1–2 min). Do this **before** the
> interview so the live launch is instant.

---

## Manual start (two terminals)

```bash
# Terminal 1 — backend (needs only Python 3, nothing else)
cd backend
python demo_server.py

# Terminal 2 — frontend
cd frontend
npm install      # first run only
npm run dev
```

---

## 3-minute interview script

Open **http://localhost:3000/evals**. Walk the five tabs left to right — the
story is *"can you trust the answer?"*.

1. **Metrics** — Headline numbers pulled from real eval runs: recall@8, MRR@8,
   citation precision/recall, per-bucket (single-chunk / multi-chunk /
   unanswerable). *"I built the evals page first — it changes how you build."*

2. **Failures** — Click any row to expand the model answer vs. gold answer diff.
   Point at **q007**: the model answered a Non-Compete question it should have
   refused. *"The system surfaces its own hallucinations — honesty over vanity
   metrics."*

3. **Experiments** — Metric trend across runs with deltas. *"Every change is an
   experiment; regressions are visible, including rolled-back ones."*

4. **Live demo** — The demo contract is pre-selected. Click a **suggested
   question** (e.g. *cap on liability*) → **Ask**. The **Trust Panel** shows the
   answer, a confidence badge, and each citation as a grounded evidence quote
   with page + chunk id. Then click *"arbitration venue"* to show a clean
   **refusal** — the contract has no arbitration clause, and the system says so.

5. **Deviation** — One run is **awaiting review**. Click **Review** to see the
   AI-drafted deviation report (contract vs. a buyer-side playbook), edit the
   summary inline, and **Approve** — the human-in-the-loop step. You can also
   start a fresh run from the picker at the top.

**One-liner:** *"RAG over contracts is commodity. The differentiator is the
grounding layer, the honest evals page, and a human-in-the-loop deviation
pipeline — the system is auditable, not just accurate."*

---

## Demo vs. real backend

| | Demo mode (`demo_server.py`) | Real backend (`app/main.py`) |
|---|---|---|
| Docker / ParadeDB | not needed | required |
| API keys (Anthropic/Voyage/Cohere) | not needed | required |
| Network | none | yes |
| Eval metrics | real files, aggregated live | real files, aggregated live |
| QA answers | curated from golden set | live retrieval + Sonnet |
| Deviation runs | seeded + interactive | live LangGraph pipeline |

To run the **real** stack, follow the Quick Start in [`README.md`](README.md)
(Docker + `.env` with keys + `uv run uvicorn app.main:app`). The frontend is
identical for both — it just points at `http://localhost:8000`.
