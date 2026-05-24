"""
Deterministic citation validator. Every LLM answer includes a list of claimed
citation references (chunk ID + character span). This module verifies that each
citation maps to a real chunk retrieved in the same request, then computes two
metrics (Spike 1 decision):

  Primary — Containment: does the cited chunk's text contain the gold character
    span as a substring? Robust to PDF layout variance and multi-span clauses
    where union-bbox IoU is inflated by whitespace. This is the CI gate metric.

  Secondary — Set-union IoU@0.5: used to measure visual Trust Panel highlight
    quality. Tracked but not CI-gated because ~15–20% of CUAD-style answers
    require multi-span citations where a single union bbox is geometrically
    misleading.

Implemented: Week 3.
"""
