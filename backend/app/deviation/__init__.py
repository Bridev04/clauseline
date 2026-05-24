"""
LangGraph deviation detection pipeline. Five nodes executed as a directed graph:

  Loader       — fetches contract chunks and playbook rules from Postgres
  Classifier   — parallel fan-out per CUAD category (Haiku); labels each clause
                 as Conforming / Deviating / Unclear
  Comparator   — parallel fan-out per deviating/unclear rule (Sonnet); produces
                 a structured comparison with evidence text and deviation type
  Scorer       — deterministic aggregation of per-rule scores into an overall
                 deviation severity (High / Medium / Low / None)
  Summarizer   — Sonnet drafts a plain-language deviation report for the reviewer

A HITL interrupt fires after Summarizer; the reviewer approves, rejects, or edits
before the result is committed. State uses `Annotated[list, add]` reducers on the
fan-in edges so parallel node outputs merge cleanly.

Implemented: Week 5 (pipeline), Week 6 (HITL + UI).
"""
