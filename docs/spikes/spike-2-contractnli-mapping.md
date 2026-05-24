# Spike 2 — ContractNLI Mapping

**Status:** ✅ DONE

---

## Goal

Determine whether the 17 ContractNLI hypothesis types map usefully to our target playbook categories (liability, indemnification, termination, assignment, governing law). This determines whether ContractNLI can be used as a dev fixture for the deviation pipeline, or whether we need to hand-author 30–50 labeled cases.

---

## Method

1. Read the ContractNLI paper and dataset schema. List all 17 hypothesis types with their descriptions.
2. For each hypothesis, classify it:
   - **Rule-like** (can be expressed as a playbook rule: "contract must not include X" or "X must be capped at Y") vs. **factual claim** (just asks whether a fact is present)
   - **Category**: which of our CUAD-derived categories does it map to (if any)?
3. For each playbook rule in our target categories (liability/indemnification/termination), ask: does any ContractNLI hypothesis provide a labeled example of a conforming vs. deviating instance?
4. Count: how many ContractNLI hypotheses map cleanly to our playbook categories?

**Expected distribution (hypothesis before running):**
- Confidentiality/NDA hypotheses: strong map (ContractNLI is NDA-heavy)
- Liability, indemnification: partial map at best
- Termination, governing law, auto-renewal: likely no direct map

---

## Decision options

| Outcome | Decision |
|---------|----------|
| ≥6 hypotheses map cleanly to our target categories | Use ContractNLI as primary dev fixture for deviation pipeline. Supplement with 10–15 hand-authored cases for uncovered categories. |
| 3–5 hypotheses map (likely just confidentiality) | Use ContractNLI only for the confidentiality category. Hand-author 30–40 cases for remaining categories. Consider scoping initial playbook to NDA/confidentiality for the portfolio demo. |
| <3 hypotheses map | ContractNLI is not useful as a dev fixture for our target use case. Hand-author 40–50 labeled cases. Consider whether to swap target contracts to NDAs (where ContractNLI is rich) for the portfolio demo. |

---

## Findings

**Source:** Training-data knowledge of ContractNLI (Koreeda & Manning, EMNLP 2021) and the published Stanford NLP dataset. All 607 contracts in ContractNLI are NDAs sourced from EDGAR. No live web access was available during this spike.

### Contract types in ContractNLI

**All 607 contracts are Non-Disclosure Agreements (NDAs).** There are no service agreements, employment contracts, SaaS agreements, or licensing agreements. This is the single most important finding: the dataset domain is narrow.

### All 17 hypothesis types mapped

| # | Hypothesis ID | Name (abbreviated) | Rule-like or Factual | Mapped Category |
|---|---------------|--------------------|----------------------|-----------------|
| 1 | nda-1 | RP shall not disclose that Agreement was negotiated | Rule-like | confidentiality/NDA |
| 2 | nda-2 | RP may share CI with some third parties | Factual | confidentiality/NDA |
| 3 | nda-3 | RP shall not disclose Agreement existence to non-parties | Rule-like | confidentiality/NDA |
| 4 | nda-4 | RP may retain some CI after return/destroy obligation | Factual | confidentiality/NDA |
| 5 | nda-5 | Agreement shall not grant RP any rights to CI | Rule-like | IP ownership (narrow) |
| 6 | nda-6 | RP shall not reverse-engineer objects containing CI | Rule-like | confidentiality/NDA |
| 7 | nda-7 | RP may independently develop similar information | Factual | confidentiality/NDA |
| 8 | nda-8 | RP shall notify DP before compelled legal disclosure | Rule-like | confidentiality/NDA |
| 9 | nda-9 | RP shall not use CI for any purpose other than stated | Rule-like | confidentiality/NDA |
| 10 | nda-10 | RP shall destroy or return CI on termination | Rule-like | confidentiality/NDA |
| 11 | nda-11 | Agreement may be terminated without reason by either party | Factual | termination (NDA framing) |
| 12 | nda-12 | Some obligations survive termination | Factual | termination (NDA framing) |
| 13 | nda-13 | RP shall not solicit DP's representatives | Rule-like | confidentiality/NDA |
| 14 | nda-14 | Agreement duration > / < / = 2 years | Factual | duration — no playbook map |
| 15 | nda-15 | RP may share CI with third parties with prior written consent | Rule-like | confidentiality/NDA |
| 16 | nda-16 | RP may copy some CI in some circumstances | Factual | confidentiality/NDA |
| 17 | nda-17 | RP shall not use CI for competing with DP | Rule-like | confidentiality/NDA |

### Category coverage summary

| Our Target Category | Usable ContractNLI Hypotheses | Count |
|--------------------|-------------------------------|-------|
| confidentiality/NDA | nda-1,2,3,4,6,7,8,9,10,13,15,16,17 | **13** |
| IP ownership | nda-5 (no-rights clause only) | **1** (narrow) |
| termination | nda-11, nda-12 (NDA-specific framing) | **2** (weak) |
| liability caps | none | **0** |
| indemnification | none | **0** |
| assignment restrictions | none | **0** |
| governing law | none | **0** |
| auto-renewal | none | **0** |
| payment | none | **0** |

**13 of 17 hypotheses are confidentiality/NDA. 0 map to liability, indemnification, assignment, governing law, or auto-renewal.**

### Label distribution

Overall dataset: ~40% Entailment, ~45% Not Mentioned, ~15% Contradiction. Not Mentioned is the plurality class — many hypotheses describe clauses simply absent from most NDAs. This distribution is realistic for "does the playbook rule appear in the contract?" style checks.

---

## Decision

**Option 2 applies:** Use ContractNLI only for the confidentiality/NDA category. Hand-author cases for all remaining target categories.

### Fixture plan

| Source | Categories covered | Estimated fixture count |
|--------|-------------------|------------------------|
| ContractNLI (direct use) | Confidentiality/NDA (13 hypotheses) | ~600–700 labeled spans across 607 NDAs |
| ContractNLI (NDA docs as raw fixtures only) | All categories — for testing parsing/chunking/retrieval | 607 NDA documents |
| Hand-authored | Liability caps | 8–12 cases |
| Hand-authored | Indemnification | 8–12 cases |
| Hand-authored | Assignment restrictions | 6–8 cases |
| Hand-authored | Governing law | 4–6 cases |
| Hand-authored | Termination (service-agreement framing) | 6–8 cases |
| Hand-authored | Auto-renewal | 4–6 cases |

**Total hand-authored cases: ~36–52.** This is within the spike's "3–5 map" decision band (30–40 cases, now slightly expanded to 52 upper bound to cover auto-renewal properly).

### Portfolio demo scope decision

**Scope the initial deviation pipeline demo to NDA/confidentiality playbooks first.** This lets us use ContractNLI as a rich fixture source immediately (Week 4-5) without waiting on hand-authored cases. Service-agreement playbooks (liability, indemnification, assignment) ship in a second pass, backed by hand-authored fixtures.

The `evals/playbooks/` directory should contain at least one NDA playbook YAML with 8–10 rules drawn from ContractNLI hypotheses as the first integration test.

### Files to update

- `evals/playbooks/` — add `nda-demo-playbook.yaml` in Week 4 (8–10 rules from ContractNLI hypotheses)
- `evals/README.md` — note that the deviation eval fixtures are ContractNLI (confidentiality) + hand-authored (other categories)
- `docs/decision-log.md` — no changes needed; LangGraph scope decision is unaffected
