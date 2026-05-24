"""
Automated risk flag detection. Four flag types with severity levels:
  1. Auto-renewal clause (Medium) — contract renews without affirmative consent
  2. Uncapped liability (High) — no ceiling on damages owed by one party
  3. Asymmetric termination rights (Medium) — one party can exit on shorter notice
  4. Assignment without consent (High) — contract can be assigned to a third party
     without the other party's approval

Flags are deterministic (regex + extraction output), not LLM-judged, so they are
cheap to run and appear in the Trust Panel. Severity thresholds are configurable
via playbook YAML overrides.

Implemented: Week 2.
"""
