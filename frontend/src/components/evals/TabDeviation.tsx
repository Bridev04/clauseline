"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DeviationRun,
  fetchDeviationRuns,
  submitDeviationReview,
} from "@/lib/api";
import { DeviationLauncher } from "@/components/DeviationLauncher";
import { UploadContract } from "@/components/UploadContract";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-red-600 bg-red-50",
  high: "text-orange-600 bg-orange-50",
  medium: "text-yellow-600 bg-yellow-50",
  low: "text-blue-600 bg-blue-50",
  none: "text-zinc-500 bg-zinc-100",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  failed: "Failed",
};

function SeverityBadge({ severity }: { severity: string | null }) {
  if (!severity) return <span className="text-zinc-400">—</span>;
  const cls = SEVERITY_COLORS[severity] ?? "text-zinc-500 bg-zinc-100";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase ${cls}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isReview = status === "awaiting_review";
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
        isReview
          ? "bg-amber-100 text-amber-700"
          : status === "completed"
          ? "bg-emerald-50 text-emerald-700"
          : status === "failed"
          ? "bg-red-50 text-red-600"
          : "bg-zinc-100 text-zinc-500"
      }`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function ReviewPanel({
  run,
  onDone,
}: {
  run: DeviationRun;
  onDone: (updated: DeviationRun) => void;
}) {
  const summary =
    (run.result as { summary?: string } | null)?.summary ?? "(no summary available)";
  const [editedSummary, setEditedSummary] = useState(summary);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(decision: "approved" | "rejected") {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await submitDeviationReview(
        run.run_id,
        decision,
        editedSummary !== summary ? editedSummary : undefined,
        notes || undefined,
      );
      onDone(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-3 border-t border-zinc-200 pt-3 space-y-3">
      <p className="text-xs font-medium text-zinc-500 uppercase tracking-wide">
        AI-generated summary — edit before approving
      </p>
      <textarea
        className="w-full text-sm font-mono bg-zinc-50 border border-zinc-200 rounded p-2 resize-y min-h-[120px] focus:outline-none focus:ring-1 focus:ring-zinc-400"
        value={editedSummary}
        onChange={(e) => setEditedSummary(e.target.value)}
        disabled={submitting}
      />
      <input
        type="text"
        placeholder="Reviewer notes (optional)"
        className="w-full text-sm border border-zinc-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-zinc-400"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        disabled={submitting}
      />
      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={() => handleSubmit("approved")}
          disabled={submitting}
          className="px-3 py-1.5 text-sm font-medium rounded bg-zinc-900 text-white hover:bg-zinc-700 disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Approve"}
        </button>
        <button
          onClick={() => handleSubmit("rejected")}
          disabled={submitting}
          className="px-3 py-1.5 text-sm font-medium rounded border border-zinc-300 text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}

function RunRow({
  run,
  onUpdated,
}: {
  run: DeviationRun;
  onUpdated: (updated: DeviationRun) => void;
}) {
  const [expanded, setExpanded] = useState(run.status === "awaiting_review");
  const [localRun, setLocalRun] = useState(run);

  function handleDone(updated: DeviationRun) {
    setLocalRun(updated);
    setExpanded(false);
    onUpdated(updated);
  }

  const createdAt = new Date(localRun.created_at).toLocaleString();

  return (
    <div className="border border-zinc-200 rounded-lg p-3 space-y-1">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs text-zinc-400 shrink-0">
            {localRun.run_id.slice(0, 8)}
          </span>
          <StatusBadge status={localRun.status} />
          <SeverityBadge severity={localRun.overall_severity} />
        </div>
        <div className="flex items-center gap-3 text-xs text-zinc-500">
          <span>{localRun.deviations_found} deviation{localRun.deviations_found !== 1 ? "s" : ""}</span>
          <span>{localRun.playbook_id}</span>
          <span>{createdAt}</span>
          {localRun.status === "awaiting_review" && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-zinc-900 font-medium hover:underline"
            >
              {expanded ? "Collapse" : "Review"}
            </button>
          )}
          {localRun.review_decision && (
            <span
              className={`font-medium ${
                localRun.review_decision === "approved" ? "text-emerald-600" : "text-red-500"
              }`}
            >
              {localRun.review_decision}
            </span>
          )}
        </div>
      </div>

      {expanded && localRun.status === "awaiting_review" && (
        <ReviewPanel run={localRun} onDone={handleDone} />
      )}
    </div>
  );
}

export function TabDeviation() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["deviation-runs"],
    queryFn: () => fetchDeviationRuns(20),
    refetchInterval: 10_000,
  });

  const [runs, setRuns] = useState<DeviationRun[] | null>(null);
  const displayRuns = runs ?? data;

  function handleUpdated(updated: DeviationRun) {
    setRuns((prev) =>
      (prev ?? data ?? []).map((r) => (r.run_id === updated.run_id ? updated : r)),
    );
    queryClient.invalidateQueries({ queryKey: ["deviation-runs"] });
  }

  if (isLoading) return <p className="text-zinc-500 text-sm">Loading deviation runs…</p>;
  if (error)
    return <p className="text-sm text-red-500">Failed to load deviation runs. Is the API running?</p>;

  const awaitingCount = (displayRuns ?? []).filter((r) => r.status === "awaiting_review").length;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Start a deviation run</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <UploadContract />
          <DeviationLauncher />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            Deviation runs
            {awaitingCount > 0 && (
              <span className="inline-block px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
                {awaitingCount} awaiting review
              </span>
            )}
          </CardTitle>
          {displayRuns && displayRuns.length > 0 ? (
            <p className="text-xs text-zinc-500">
              {displayRuns.length} run{displayRuns.length !== 1 ? "s" : ""} — newest first. Runs in{" "}
              <span className="font-medium text-amber-700">awaiting review</span> can be approved or
              rejected inline.
            </p>
          ) : (
            <p className="text-xs text-zinc-400">No runs yet — start one above.</p>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {(displayRuns ?? []).map((run) => (
            <RunRow key={run.run_id} run={run} onUpdated={handleUpdated} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
