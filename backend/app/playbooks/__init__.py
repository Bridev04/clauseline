"""
Playbook YAML loader and schema validation. A playbook is a structured description
of a customer's acceptable contract positions — e.g., "governing law must be
California", "liability cap must be ≥ 2× contract value". Playbooks live in
`data/playbooks/yaml/` (production) and `evals/playbooks/` (eval fixtures).
The schema is defined with Pydantic v2 so validation errors surface at load time,
not during a deviation run. Supports per-category severity overrides for the
flag layer.

Implemented: Week 4.
"""
