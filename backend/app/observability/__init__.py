"""
Langfuse observability client. Every LLM call in the system is traced through
this module: input tokens, output tokens, model, latency, cost estimate, and the
Langfuse generation ID that links back to the full trace in the Langfuse UI.
The eval failure explorer in `/evals` tab 2 embeds Langfuse trace links so that
each failure can be inspected end-to-end without switching tools. The client is
initialized at app startup (see `main.py` lifespan) and injected via FastAPI
dependency injection.

Implemented: Week 1 (client), Week 3 (eval integration).
"""
