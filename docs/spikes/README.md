# Validation Spikes

## Why spikes exist

Two kinds of assumptions are dangerous: ones that are expensive to discover wrong (architecture) and ones that seem obvious but aren't (data reality). Spikes are cheap, time-boxed experiments run *before* Week 1 code so that the real implementation doesn't build on a false premise.

Two specific assumptions motivated this spike round:

1. **Citation gold realism (Spike 1):** The citation IoU metric assumes that a correct answer maps to a bounded region in the PDF. If real contract answers require citing five scattered paragraphs, IoU@0.5 against a single bbox is not a useful metric — it needs to be redesigned before the citation validator is built.

2. **ContractNLI mapping (Spike 2):** ContractNLI is a natural candidate for dev fixtures because it has labeled hypotheses over real contracts. But the 17 hypotheses are concentrated in confidentiality/NDA territory. If they don't map to our target playbook categories (liability, indemnification, termination), the dev fixture assumption is wrong.

Spike 3 and 5 are structural: Spike 3 produces the final category list (can't write evaluation code without it), and Spike 5 verifies the database query shape (can't write retrieval code without it).

Spike 4 was meta — it existed to force the README outline before any code, and is now done.

---

## Status

| # | Name | Status | Decision |
|---|------|--------|----------|
| 1 | Citation reality check | ✅ done | Containment is primary metric; IoU@0.5 demoted to secondary (visual only) |
| 2 | ContractNLI mapping | ✅ done | Use for confidentiality only; hand-author 36–52 cases for other categories; demo NDA playbook first |
| 3 | ContractEval overlap → category list | ✅ done | Final 12 categories confirmed (see spike-3); CUAD RoBERTa-large F1 is the baseline |
| 4 | README outline | ✅ done | Root README is the deliverable |
| 5 | pg_search install verification | ✅ done | pg_search 0.23.4 + vector 0.8.1 confirmed; fused RRF CTE works; `content:term` syntax required |

---

## Decision rule format

Each spike has a **decision rule** written before the experiment runs. This forces clarity about what outcome would change the design. A spike without a pre-written decision rule is just exploration — useful, but not the same thing.
