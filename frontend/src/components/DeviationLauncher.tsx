"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchContracts, fetchPlaybooks, startDeviationRun } from "@/lib/api";

export function DeviationLauncher() {
  const queryClient = useQueryClient();
  const [contractId, setContractId] = useState("");
  const [playbookId, setPlaybookId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: contracts } = useQuery({
    queryKey: ["contracts"],
    queryFn: fetchContracts,
  });

  const { data: playbooks } = useQuery({
    queryKey: ["playbooks"],
    queryFn: fetchPlaybooks,
  });

  const readyContracts = contracts?.filter((c) => c.status === "ready") ?? [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!contractId || !playbookId) return;
    setSubmitting(true);
    setError(null);
    try {
      await startDeviationRun(contractId, playbookId);
      setContractId("");
      setPlaybookId("");
      await queryClient.invalidateQueries({ queryKey: ["deviation-runs"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-zinc-500 mb-1">Contract</label>
        <select
          className="w-full rounded border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
          value={contractId}
          onChange={(e) => setContractId(e.target.value)}
          disabled={submitting}
        >
          <option value="">Select a contract…</option>
          {readyContracts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.filename}
            </option>
          ))}
        </select>
        {readyContracts.length === 0 && (
          <p className="text-xs text-zinc-400 mt-1">No ready contracts — upload one above.</p>
        )}
      </div>

      <div>
        <label className="block text-xs font-medium text-zinc-500 mb-1">Playbook</label>
        <select
          className="w-full rounded border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
          value={playbookId}
          onChange={(e) => setPlaybookId(e.target.value)}
          disabled={submitting}
        >
          <option value="">Select a playbook…</option>
          {playbooks?.map((pb) => (
            <option key={pb.id} value={pb.id}>
              {pb.name} (v{pb.version}, {pb.rule_count} rules)
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <button
        type="submit"
        disabled={!contractId || !playbookId || submitting}
        className="px-4 py-2 rounded bg-zinc-800 text-white text-sm font-medium disabled:opacity-40 hover:bg-zinc-700 transition-colors"
      >
        {submitting ? "Starting…" : "Start deviation run"}
      </button>
    </form>
  );
}
