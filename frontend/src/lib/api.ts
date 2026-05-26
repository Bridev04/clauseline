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

export interface ExperimentDelta {
  pass_rate: number;
  recall_at_8: number;
  mrr_at_8: number;
  containment_precision: number;
  containment_recall: number;
}

export interface ExperimentRun {
  run_id: string;
  started_at: string;
  question_count: number;
  pass_rate: number;
  recall_at_8: number;
  mrr_at_8: number;
  containment_precision: number;
  containment_recall: number;
  delta: ExperimentDelta | null;
}

export async function fetchExperiments(): Promise<ExperimentRun[]> {
  const res = await fetch(`${API_BASE}/api/evals/experiments`);
  if (!res.ok) throw new Error(`Experiments request failed: ${res.status}`);
  return res.json();
}

export async function fetchContracts(): Promise<{ id: string; filename: string; status: string }[]> {
  const res = await fetch(`${API_BASE}/api/contracts/`);
  if (!res.ok) throw new Error(`Contracts request failed: ${res.status}`);
  const data: { contract_id: string; filename: string; status: string }[] = await res.json();
  return data.map((c) => ({ id: c.contract_id, filename: c.filename, status: c.status }));
}

export interface DeviationRun {
  run_id: string;
  contract_id: string;
  playbook_id: string;
  status: string;
  overall_severity: string | null;
  deviations_found: number;
  result: Record<string, unknown> | null;
  review_decision: string | null;
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlaybookSummary {
  id: string;
  name: string;
  version: string;
  description: string | null;
  rule_count: number;
}

export async function fetchPlaybooks(): Promise<PlaybookSummary[]> {
  const res = await fetch(`${API_BASE}/api/playbooks/`);
  if (!res.ok) throw new Error(`Playbooks request failed: ${res.status}`);
  return res.json();
}

export async function uploadContract(file: File): Promise<{ id: string; filename: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/contracts/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Upload failed: ${res.status}`);
  }
  const data: { contract_id: string; filename: string; status: string } = await res.json();
  return { id: data.contract_id, filename: data.filename, status: data.status };
}

export async function startDeviationRun(
  contractId: string,
  playbookId: string,
): Promise<DeviationRun> {
  const res = await fetch(`${API_BASE}/api/deviation/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id: contractId, playbook_id: playbookId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Deviation run failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchDeviationRuns(limit = 20, status?: string): Promise<DeviationRun[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/api/deviation/runs?${params}`);
  if (!res.ok) throw new Error(`Deviation runs request failed: ${res.status}`);
  return res.json();
}

export async function submitDeviationReview(
  runId: string,
  decision: "approved" | "rejected",
  editedSummary?: string,
  notes?: string,
): Promise<DeviationRun> {
  const res = await fetch(`${API_BASE}/api/deviation/${runId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision,
      edited_summary: editedSummary ?? null,
      notes: notes ?? null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Review failed: ${res.status}`);
  }
  return res.json();
}
