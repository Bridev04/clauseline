"""
Structured extraction of the 12 CUAD categories chosen via Spike 3. Each category
(e.g., governing law, limitation of liability, auto-renewal, assignment) is extracted
as a typed `ExtractionResult` with the clause text, page reference, and a confidence
signal. Uses Haiku for the initial extraction pass and Sonnet for low-confidence
re-checks. The final 12-category list is the output of Spike 3 — do not expand
or contract the list without updating the golden eval set.

Implemented: Week 2.
"""
