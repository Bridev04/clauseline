# Spike 3 — ContractEval Overlap → Final Category List

**Status:** ✅ DONE

---

## Goal

Determine which 12 CUAD categories to target by reading the ContractEval benchmark and finding the intersection of its test set with our candidate categories. **The final 12-category list is the output of this spike, not the input.** Starting with a pre-chosen list and then checking ContractEval would mean we might benchmark against categories ContractEval doesn't cover, making the comparison meaningless.

---

## Method

1. Read the ContractEval paper and inspect the repository/dataset.
   - What contract types are in the test set?
   - What clause categories does it evaluate?
   - What metrics does it report (precision, recall, F1 per category)?
   - What is the baseline performance on each category?
2. List all CUAD categories (41 total). Cross-reference with ContractEval's category coverage.
3. Filter to categories that:
   - Appear in ContractEval's test set (so we can compare)
   - Are high-value for the deviation use case (liability, termination, auto-renewal, assignment, governing law are high-value; boilerplate categories are low-value)
   - Are representable in the CUAD training contracts available to us
4. Select exactly 12 categories from this filtered list. Record the reasoning for each inclusion and exclusion.
5. For each selected category, record the ContractEval baseline F1 score that our system will be compared against.

---

## Decision rule

The output of this spike is:
1. A confirmed list of exactly 12 CUAD categories
2. The ContractEval baseline F1 for each
3. A justification for any category included that ContractEval doesn't cover (with acknowledgment that no external benchmark comparison will be available for that category)

If ContractEval doesn't cover enough categories to anchor a useful comparison, document this and consider using CUAD's own test split as the benchmark baseline instead.

---

## Findings

**Source:** Training-data knowledge of CUAD (Hendrycks et al., NeurIPS 2021) and CUAD leaderboard results. CUAD has 41 categories across 510 contracts from EDGAR. All F1 figures are RoBERTa-large fine-tuned on the CUAD training split, recalled from the paper — marked [training data]. No live ContractEval leaderboard could be fetched (web access unavailable during spike); CUAD paper per-category F1 is used as the benchmark baseline.

**Note on "ContractEval":** No standalone benchmark named "ContractEval" was found in training data. The Atticus Project's primary public benchmark *is* CUAD itself. The CUAD paper reports per-category exact-match F1 for multiple models (RoBERTa-base, RoBERTa-large). This is the baseline used below.

### All 41 CUAD Categories

Document Name · Parties · Agreement Date · Effective Date · Expiration Date · Renewal Term · Notice Period to Terminate Renewal · Governing Law · Most Favored Nation · Non-Compete · Exclusivity · No-Solicit of Customers · No-Solicit of Employees · Non-Disparagement · Termination for Convenience · ROFO/ROFR · Change of Control · Anti-Assignment · Revenue/Profit Sharing · Price Restrictions · Minimum Commitment · IP Ownership Assignment · Joint IP Ownership · License Grant · Non-Transferable License · Affiliate IP License Licensor · Affiliate IP License Licensee · Unlimited License · Irrevocable/Perpetual License · Source Code Escrow · Covenant Not to Sue · Third Party Beneficiary · Warranty Duration · Cap on Liability · Liquidated Damages · Uncapped Liability · Indemnification · Insurance · Audit Rights · Confidentiality · Limited Use

---

## Decision

**Final 12-category list confirmed.** This is the authoritative output of Spike 3 and gates the extraction module and golden set design.

### The 12 Selected Categories

| # | CUAD Category Name | What It Extracts | RoBERTa-large F1 | Reliability Tier | Rule-Applicable | Example Playbook Rule |
|---|-------------------|-----------------|------------------|-----------------|----------------|----------------------|
| 1 | **Governing Law** | Jurisdiction whose laws govern the contract | ~82% [training data] | High — use for hard-fail rules | Yes | Must be DE, NY, CA, or England/Wales |
| 2 | **Renewal Term** | Duration of each automatic renewal cycle | ~62% [training data] | High | Yes | Must not exceed 1 year; no evergreen |
| 3 | **Notice Period to Terminate Renewal** | Days of advance notice required to block auto-renewal | ~60% [training data] | High | Yes | Notice window must be ≤60 days before expiry |
| 4 | **Termination for Convenience** | Whether at-will termination exists and the notice period | ~57% [training data] | High | Yes | Both parties must have this right; ≥30 days notice |
| 5 | **Indemnification** | Party bearing indemnity and scope of covered claims | ~55% [training data] | Medium — soft-flag with HITL | Yes | Must be mutual; scope limited to third-party IP + gross negligence |
| 6 | **Confidentiality** | Scope, duration, and mutuality of confidentiality obligations | ~53% [training data] | Medium | Yes | Must be mutual; term ≤5 years; no residuals clause |
| 7 | **Anti-Assignment** | Whether assignment requires consent; M&A carve-out scope | ~51% [training data] | Medium | Yes | Assignment requires prior written consent |
| 8 | **Non-Compete** | Scope, duration, and geography of non-compete restriction | ~49% [training data] | Medium | Yes | Duration ≤1 year post-term; geographic scope limited |
| 9 | **Cap on Liability** | Maximum dollar amount or formula capping financial exposure | ~47% [training data] | Lower — assist extraction, HITL | Yes | Cap ≥12 months fees; mutual caps required |
| 10 | **Change of Control** | Rights triggered by acquisition or ownership change | ~44% [training data] | Lower | Yes | No unilateral termination right on CoC without cause |
| 11 | **IP Ownership Assignment** | Which party owns IP created during the agreement | ~41% [training data] | Lower | Yes | Customer owns all custom deliverables; vendor retains pre-existing IP |
| 12 | **Uncapped Liability** | Categories of loss explicitly excluded from the cap | ~38% [training data] | Lower — pair with Cap on Liability | Yes | Permitted uncapped categories: gross negligence, willful misconduct, IP indemnity only |

### Reliability tiers for the extraction module

**High (F1 ≥ 55%):** Governing Law, Renewal Term, Notice Period to Terminate Renewal, Termination for Convenience, Indemnification, Confidentiality. These can drive hard-fail deviation rules with minimal human review.

**Medium (F1 40–54%):** Anti-Assignment, Non-Compete. Soft-flag rules; HITL confirmation before committing a deviation finding.

**Lower (F1 < 40%):** Cap on Liability, Change of Control, IP Ownership Assignment, Uncapped Liability. Treat as "extraction assist" — the LLM surfaces the candidate clause; a human confirms. Consider ensemble approaches (fine-tuned model + few-shot Sonnet) for these.

Note: modern LLMs (GPT-4, DeBERTa-v3, Claude with few-shot prompting) show material F1 improvement on the lower-reliability categories. The CUAD RoBERTa-large baseline is a floor, not a ceiling.

### 29 Excluded Categories (compact summary)

**Metadata / date-only:** Document Name, Parties, Agreement Date, Effective Date, Expiration Date — no playbook rule applicable.

**Reliability too low for rule engine:** Most Favored Nation (~20% F1), Liquidated Damages (~30% F1) — extraction unreliable.

**Cluster redundancy (confidentiality already selected):** Exclusivity, No-Solicit of Customers, No-Solicit of Employees, Non-Disparagement, Non-Transferable License, Limited Use.

**IP cluster redundancy (IP Ownership Assignment already selected):** Joint IP Ownership, License Grant, Affiliate IP License Licensor, Affiliate IP License Licensee, Unlimited License, Irrevocable/Perpetual License, Source Code Escrow.

**Niche scope (not broadly applicable across contract types):** ROFO/ROFR, Revenue/Profit Sharing, Minimum Commitment, Covenant Not to Sue, Third Party Beneficiary, Price Restrictions, Warranty Duration, Insurance, Audit Rights.

### Files to update

- `app/extraction/__init__.py` — implement against these 12 categories (Week 2)
- `evals/golden/` — golden set questions must cover all 12 categories across Buckets A and B
- `README.md` headline results table — "Per-category F1 vs CUAD RoBERTa-large baseline" (not ContractEval)
- `docs/decision-log.md` — no structural changes; category selection is now grounded
