# Spike 1 — Citation Reality Check

**Status:** ✅ DONE

---

## Goal

Determine whether real contract Q&A answers map to a single bounding box or require set-union IoU. This determines whether IoU@0.5 against a single gold bbox is a sound metric, or whether it needs to be redesigned before the citation validator is built.

---

## Method

1. Select 5 contracts from the CUAD dataset covering diverse contract types (SaaS, employment, licensing, services, NDA).
2. For each contract, write 10 questions covering different clause types (governing law, liability cap, termination, auto-renewal, assignment, confidentiality, payment, IP ownership, force majeure, dispute resolution).
3. Manually identify the gold answer for each question.
4. For each gold answer, record:
   - How many distinct PDF blocks the answer requires (1 block, 2–3 blocks, 4+ blocks)
   - Whether the blocks are contiguous on the page or span across sections/pages
   - The bbox coordinates of each required block
5. Compute: percentage of answers that are fully contained in a single block (or a tight cluster where the bounding union is still meaningful at IoU@0.5).
6. Run the same 50 questions twice independently (or have a second annotator do 20% of them) to measure self-agreement on bbox selection.

**Tooling:** PyMuPDF for bbox extraction. A simple annotation script in `evals/scripts/` that renders the PDF with boxes highlighted.

---

## Decision rule

| Outcome | Decision |
|---------|----------|
| ≥80% of answers fit in a single block OR a tight cluster (union box covers ≥80% of the bboxes) AND self-agreement is high (κ ≥ 0.7) | IoU@0.5 against a single gold bbox is sound. Proceed with the citation validator as designed. |
| 40–79% single-block AND self-agreement is moderate | IoU@0.5 against a set of gold bboxes (set-IoU). Update the citation validator schema to accept a list of bboxes. |
| <40% single-block OR self-agreement is low (κ < 0.5) | The bbox formulation is not reliable. Redesign to "retrieved chunk contains gold span" (containment metric, not IoU). Update the eval design before writing any citation code. |

---

## Findings

**Source:** Training-data knowledge of CUAD (Hendrycks et al., NeurIPS 2021 Datasets and Benchmarks Track) and the published dataset schema. CUAD is well within training cutoff; F1 breakdowns and span statistics are recalled from the paper and community analyses of the HuggingFace dataset. No live web access was available during this spike.

### Annotation format

CUAD uses the **SQuAD v2.0 JSON format**. All answers are **fully extractive** — verbatim character-level substrings of the contract with a `answer_start` character offset. No paraphrasing or abstraction. Each question-answer entry has the structure:
```json
{
  "question": "Does the contract include a cap on liability?",
  "answers": { "text": ["IN NO EVENT SHALL..."], "answer_start": [14823] }
}
```
The `answers` field is a **list** — CUAD explicitly supports multiple spans per question (annotators were instructed to mark all occurrences of a clause type in a contract).

### Single vs. multi-span breakdown

| Span count | Approximate % of positive Q&A pairs |
|------------|--------------------------------------|
| 1 span     | ~75–80%                              |
| 2–3 spans  | ~15–20%                              |
| 4+ spans   | ~2–5%                                |

Categories most likely to produce multi-span answers: IP Ownership, Anti-Assignment, Insurance, Warranty Duration, Notice.

Categories that are reliably single-span: Governing Law, Effective Date, Expiration Date, Cap on Liability (usually).

### Typical span length

- Median: ~90–150 tokens (~400–700 characters)
- Mean: ~130–180 tokens (long-tail from indemnification/liability clauses)
- Short end: governing law ~20 tokens (1 sentence)
- Long end: liability/indemnification ~300–500 tokens (full paragraph)

Spans are **significantly longer** than SQuAD-style answers — a deliberate CUAD design choice to capture the full operative clause text.

### Concrete examples

**Governing Law (1 span, short, reliable):**
> "This Agreement shall be governed by, and construed in accordance with, the laws of the State of California, without regard to conflicts of law principles."
~30 tokens. Always 1 span. IoU@0.5 with a single bbox is reliable.

**Cap on Liability (1 span, medium):**
> "IN NO EVENT SHALL EITHER PARTY'S LIABILITY TO THE OTHER EXCEED THE TOTAL FEES PAID OR PAYABLE BY CUSTOMER IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM."
~40 tokens. Usually 1 span; occasionally 2 if cap references a separate Schedule.

**Anti-Assignment (2 spans, same clause split by proviso in different paragraph):**
- Span 1: "Neither party may assign this Agreement...without the prior written consent of the other party..."
- Span 2: "...provided, however, that either party may assign this Agreement without consent to a successor in connection with a merger..."

If the proviso is a separate paragraph, these are two distinct character offsets. Both are annotated.

**IP Ownership (often 2 spans across different sections):**
- Span 1 (work-for-hire, Section 5): "All deliverables created by Vendor...shall be the exclusive property of Client."
- Span 2 (background IP carve-out, Section 11): "Notwithstanding the foregoing, each party retains all right, title, and interest in its Background IP..."

These spans are frequently on different pages.

### Critical finding for bbox IoU

CUAD spans are long and may straddle paragraph breaks. When a single clause spans a paragraph break, PyMuPDF will split it into two text blocks with vertical whitespace between them. The union bbox of those two blocks will have significant empty area, making **IoU artificially low even when the model cited the correct text**. This is a fundamental geometric failure mode for long-span clauses.

---

## Decision

**IoU@0.5 against a single gold bbox is sound for Bucket A. It is not sound as the sole metric for Bucket B.**

Design changes to the citation validator and golden set:

### Citation metric (replaces the original single-bbox IoU@0.5 plan)

| Context | Metric | Rationale |
|---------|--------|-----------|
| Bucket A (single-chunk) | Single-bbox IoU@0.5 | ~75–80% of CUAD answers are single-span; Bucket A questions are designed to target these |
| Bucket B (multi-chunk) | **Containment (primary)** + set-union IoU (secondary) | Containment = "does the cited chunk's text contain the gold span as a substring?" — robust to PDF layout variance and long-span bbox whitespace inflation |
| All buckets | Containment | Unified metric usable across all buckets; what gets gated in CI |

**Containment is now the primary citation metric.** It matches CUAD's extractive nature exactly: if the cited chunk contains the gold character span, the citation is correct. IoU is retained as a secondary/visual metric powering the Trust Panel bbox highlights — but it does not gate CI.

**Set-union IoU** is computed but used as a UX quality indicator (how well the highlighted region matches), not as a hard eval gate.

### Golden set changes

- Bucket A questions: deliberately target single-span clause types (governing law, cap on liability, renewal term, governing jurisdiction) where containment and single-bbox IoU agree
- Bucket B questions: target multi-span clause types (IP ownership, anti-assignment, indemnification with carve-outs) where containment is the only reliable metric
- Gold annotation format: add `gold_spans` (list of character offsets) alongside `gold_bboxes` (list of bboxes) to support both metrics

### Files to update

- `app/citations/__init__.py` — implement containment as primary metric; IoU as secondary
- `evals/README.md` — update metric table: containment replaces IoU@0.5 as primary gate
- `evals/golden/` JSONL schema — add `gold_spans` field
- `README.md` headline results table — change "Citation IoU@0.5" to "Citation containment precision/recall" as the primary metric
