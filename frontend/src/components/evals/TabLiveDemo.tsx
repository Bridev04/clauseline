"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrustPanel } from "@/components/TrustPanel";
import { UploadContract } from "@/components/UploadContract";
import { askQuestion, fetchContracts, type QAResponse } from "@/lib/api";

export function TabLiveDemo() {
  const [contractId, setContractId] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QAResponse | null>(null);

  const { data: contracts } = useQuery({
    queryKey: ["contracts"],
    queryFn: fetchContracts,
  });

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => askQuestion(contractId, question),
    onSuccess: (data) => setResult(data),
  });

  const canSubmit = contractId && question.trim().length > 0 && !isPending;

  return (
    <div className="space-y-4 max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload a contract</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadContract onUploaded={(id) => setContractId(id)} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ask a question</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Contract</label>
            <select
              className="w-full rounded border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
            >
              <option value="">Select a contract…</option>
              {contracts?.map((c) => (
                <option key={c.id} value={c.id} disabled={c.status !== "ready"}>
                  {c.filename} {c.status !== "ready" ? `(${c.status})` : ""}
                </option>
              ))}
            </select>
            {(!contracts || contracts.length === 0) && (
              <p className="text-xs text-zinc-400 mt-1">
                No contracts indexed yet. Upload a PDF via <code className="font-mono">POST /api/contracts/upload</code>.
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Question</label>
            <textarea
              className="w-full rounded border border-zinc-300 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-400"
              rows={3}
              placeholder="What is the governing law of this agreement?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canSubmit) mutate();
              }}
            />
          </div>

          <button
            disabled={!canSubmit}
            onClick={() => mutate()}
            className="px-4 py-2 rounded bg-zinc-800 text-white text-sm font-medium disabled:opacity-40 hover:bg-zinc-700 transition-colors"
          >
            {isPending ? "Asking…" : "Ask"}
          </button>

          {error && (
            <p className="text-sm text-red-500">
              {error instanceof Error ? error.message : "Request failed"}
            </p>
          )}
        </CardContent>
      </Card>

      {result && <TrustPanel result={result} />}
    </div>
  );
}
