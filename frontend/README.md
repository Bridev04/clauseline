# Frontend

Scaffolded in Week 3.

Stack: Next.js + TanStack Query + Recharts + shadcn/ui.

Do not run `create-next-app` until the QA API endpoint (`/api/qa/ask`) is
implemented and returning real responses, so the frontend has something concrete
to integrate against.

See `docs/architecture.md` for the planned UI surfaces:
- **Trust Panel** — answer + citations + risk flags
- **`/evals` page (4 tabs)** — metrics, failure explorer, experiments timeline, live demo
