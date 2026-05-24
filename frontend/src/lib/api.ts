const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Citation {
  chunk_id: string;
  quoted_text: string;
  page: number;
  is_grounded: boolean;
}

export interface QAResponse {
  contract_id: string;
  question: string;
  answer: string;
  citations: Citation[];
  confidence: "high" | "medium" | "low" | "none";
  retrieved_count: number;
  trace_id: string | null;
}

export interface BucketSummary {
  bucket: string;
  count: number;
  recall_at_8: number;
  containment_precision: number;
  containment_recall: number;
  pass_rate: number;
}

export interface EvalSummary {
  total_questions: number;
  pass_rate: number;
  recall_at_8: number;
  mrr_at_8: number;
  containment_precision: number;
  containment_recall: number;
  per_bucket: BucketSummary[];
  run_count: number;
}

export interface FailureEntry {
  question_id: string;
  contract_id: string;
  question: string;
  bucket: string;
  cuad_category: string;
  answer: string;
  gold_answer: string;
  citations: Record<string, unknown>[];
  gold_spans: Record<string, unknown>[];
  retrieved_chunk_ids: string[];
  recall_at_8: number;
  containment_precision: number;
  containment_recall: number;
  trace_id: string | null;
  failure_reason: string | null;
  timestamp: string;
}

export async function askQuestion(contractId: string, question: string): Promise<QAResponse> {
  const res = await fetch(`${API_BASE}/api/qa/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id: contractId, question }),
  });
  if (!res.ok) throw new Error(`QA request failed: ${res.status}`);
  return res.json();
}

export async function fetchEvalSummary(): Promise<EvalSummary> {
  const res = await fetch(`${API_BASE}/api/evals/summary`);
  if (!res.ok) throw new Error(`Eval summary failed: ${res.status}`);
  return res.json();
}

export async function fetchFailures(
  limit = 50,
  offset = 0,
  bucket?: string
): Promise<FailureEntry[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (bucket) params.set("bucket", bucket);
  const res = await fetch(`${API_BASE}/api/evals/failures?${params}`);
  if (!res.ok) throw new Error(`Failures request failed: ${res.status}`);
  return res.json();
}

export async function fetchContracts(): Promise<{ id: string; filename: string; status: string }[]> {
  const res = await fetch(`${API_BASE}/api/contracts/`);
  if (!res.ok) throw new Error(`Contracts request failed: ${res.status}`);
  return res.json();
}
