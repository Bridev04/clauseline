"""
Anthropic LLM client with tier routing. All calls go through this module so that
Langfuse tracing, retry logic (tenacity), and model selection live in one place.
Routing rule: Haiku 4.5 for classification, extraction, and high-volume passes;
Sonnet 4.6 for QA answers, playbook comparisons, and deviation summaries where
accuracy is load-bearing. The tier is selected by the caller via a `Tier` enum,
not by hardcoding model strings outside this module.

Implemented: Week 1 (client setup), Week 3 (QA routing), Week 5 (deviation routing).
"""
