# Evals

The `/evals` page is not an afterthought — it is the portfolio moat. It gets built early (Week 3) because it changes what you instrument, what you log, and what you call a failure. This directory holds everything needed to produce and display that page.

---

## The four-tab philosophy

**Tab 1 — Headline metrics + per-bucket breakdown**
Top-line numbers (recall@8, citation IoU, Ragas faithfulness, refusal accuracy) broken down by the three golden-set buckets. Comparison column against the ContractEval baseline. Numbers update after each eval run; the baseline JSON is pinned and committed.

**Tab 2 — Failure explorer**
Every question where the system failed, with:
- The retrieved chunks (what the model saw)
- The generated answer (what it said)
- The gold answer (what it should have said)
- A link to the Langfuse trace (full token-level inspection)
- A written analysis field (filled during manual review)

This tab exists because aggregate metrics hide *which* failures matter. A 0.05 drop in faithfulness is invisible in Tab 1 but five specific, instructive failures in Tab 2.

**Tab 3 — Experiments timeline**
Every eval run ever committed, in chronological order, including rolled-back experiments. Each entry shows: hypothesis, what changed, before/after deltas, and a verdict (kept / rolled back / ongoing). Rolled-back entries stay in the timeline — they are evidence, not embarrassments.

**Tab 4 — Live demo with Trust Panel**
A real query box connected to the live backend. Answers include the Trust Panel: cited evidence with bounding-box highlights, confidence indicators, and active risk flags. This is the public-facing face of the system.

---

## Layered eval strategy

| Layer | Metric | Method | Deterministic? |
|-------|--------|--------|----------------|
| Retrieval | recall@8 | gold chunk in top-8? | Yes |
| Retrieval | MRR@8 | rank of first gold chunk | Yes |
| Citation | Containment precision | cited chunk text contains gold span | Yes (string match) |
| Citation | Containment recall | gold span covered by any cited chunk | Yes (string match) |
| Citation | Set-union IoU@0.5 | bbox union overlap — visual quality indicator | Yes (bbox math) — tracked, not CI-gated |
| Generation | Ragas faithfulness | every claim in answer supported by context? | LLM-judge |
| Generation | Ragas answer relevance | does the answer address the question? | LLM-judge |
| Generation | Refusal accuracy | does the model say "I don't know" on unanswerable? | Yes |
| Latency/cost | p95 latency | wall-clock, end-to-end | Yes |
| Latency/cost | $/query | token cost at current pricing | Yes |

---

## Golden set design

**60 questions, 3 buckets of 20:**

- **Bucket A — Single-chunk** answers: the gold evidence lives entirely within one clause-level chunk. Deliberately targets single-span CUAD clause types (governing law, cap on liability, renewal term). IoU@0.5 and containment agree here.
- **Bucket B — Multi-chunk** answers: the gold evidence spans two or more chunks, possibly across sections. Deliberately targets multi-span-prone CUAD categories (IP ownership, anti-assignment, indemnification with carve-outs). **Containment is the only reliable metric here** — single-bbox IoU fails on multi-span clauses due to whitespace inflation in the union bbox (see Spike 1).
- **Bucket C — Unanswerable**: the question cannot be answered from the contract. Tests refusal. The model must say "I don't know" or equivalent — any fabricated answer is a hard failure.

Question format: `evals/golden/*.jsonl`, one JSON object per line:
```json
{
  "id": "q001",
  "contract": "contract_filename.pdf",
  "question": "...",
  "bucket": "A",
  "cuad_category": "Governing Law",
  "gold_answer": "...",
  "gold_chunks": ["chunk_id_1"],
  "gold_spans": [{"start": 14823, "text": "This Agreement shall be governed by..."}],
  "gold_bboxes": [{"page": 3, "x0": 72, "y0": 144, "x1": 540, "y1": 200}]
}
```

`gold_spans` is the primary citation metric input (containment check). `gold_bboxes` drives the visual Trust Panel highlights. Both are required. `cuad_category` maps to one of the 12 categories from Spike 3.

---

## CI merge gate

The eval gate lands in CI **Week 6**. It:
1. Runs the full 60-question golden set
2. Computes each metric
3. Repeats LLM-judge metrics 3× and takes `mean − 1·stddev`
4. Compares against `evals/results/baseline.json`
5. Fails the PR if any deterministic metric regresses, or if any LLM-judge adjusted score drops below baseline

The `--run-evals` pytest marker gates the expensive runs so unit tests stay fast.

---

## Directory layout

```
evals/
├── golden/        JSONL question sets (committed, version-controlled)
├── results/       Eval run outputs as JSON (committed; gitignore *.json except .gitkeep)
├── playbooks/     Eval-only playbook fixtures (not production data)
├── annotations/   Hand-labeled bbox annotations from the annotation tool
└── scripts/       run_eval.py and helpers
```
