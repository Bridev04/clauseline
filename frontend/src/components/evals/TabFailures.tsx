"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchFailures, type FailureEntry } from "@/lib/api";

const BUCKET_COLORS: Record<string, string> = {
  A: "bg-blue-100 text-blue-800",
  B: "bg-amber-100 text-amber-800",
  C: "bg-red-100 text-red-800",
};

function FailureRow({ entry }: { entry: FailureEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-zinc-50"
        onClick={() => setExpanded((v) => !v)}
      >
        <TableCell className="font-mono text-xs">{entry.question_id}</TableCell>
        <TableCell>
          <span
            className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${BUCKET_COLORS[entry.bucket] ?? ""}`}
          >
            {entry.bucket}
          </span>
        </TableCell>
        <TableCell className="text-sm max-w-xs truncate">{entry.question}</TableCell>
        <TableCell className="text-xs text-zinc-500">{entry.cuad_category}</TableCell>
        <TableCell className="text-xs font-mono">{(entry.recall_at_8 * 100).toFixed(0)}%</TableCell>
        <TableCell className="text-xs font-mono">
          {(entry.containment_recall * 100).toFixed(0)}%
        </TableCell>
        <TableCell className="text-xs text-zinc-400">{entry.failure_reason ?? "-"}</TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-zinc-50 p-0">
            <div className="p-4 space-y-3 text-sm">
              <div>
                <p className="font-medium text-xs text-zinc-500 mb-1">Model answer</p>
                <p className="text-zinc-800">{entry.answer || <em>empty</em>}</p>
              </div>
              <div>
                <p className="font-medium text-xs text-zinc-500 mb-1">Gold answer</p>
                <p className="text-zinc-800">{entry.gold_answer}</p>
              </div>
              {entry.gold_spans.length > 0 && (
                <div>
                  <p className="font-medium text-xs text-zinc-500 mb-1">Gold spans</p>
                  <ul className="space-y-1">
                    {entry.gold_spans.map((s, i) => (
                      <li key={i} className="font-mono text-xs bg-white border border-zinc-200 rounded px-2 py-1">
                        &ldquo;{String((s as { text?: string }).text ?? "")}&rdquo;
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {entry.trace_id && (
                <p className="text-xs text-zinc-400 font-mono">
                  Trace: {entry.trace_id}
                </p>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export function TabFailures() {
  const [bucket, setBucket] = useState<string | undefined>(undefined);
  const { data, isLoading, error } = useQuery({
    queryKey: ["eval-failures", bucket],
    queryFn: () => fetchFailures(50, 0, bucket),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {[undefined, "A", "B", "C"].map((b) => (
          <button
            key={b ?? "all"}
            onClick={() => setBucket(b)}
            className={`px-3 py-1 rounded text-sm border transition-colors ${
              bucket === b
                ? "bg-zinc-800 text-white border-zinc-800"
                : "bg-white text-zinc-600 border-zinc-300 hover:border-zinc-500"
            }`}
          >
            {b ?? "All"}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-zinc-500 text-sm">Loading failures…</p>}
      {error && <p className="text-red-500 text-sm">Failed to load failures.</p>}

      {data && data.length === 0 && (
        <p className="text-zinc-500 text-sm">No failures found — run the eval harness first.</p>
      )}

      {data && data.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{data.length} failure{data.length !== 1 ? "s" : ""}</CardTitle>
            <p className="text-xs text-zinc-500">Click a row to expand the full answer diff.</p>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">ID</TableHead>
                  <TableHead className="w-14">Bucket</TableHead>
                  <TableHead>Question</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead className="w-20">R@8</TableHead>
                  <TableHead className="w-24">Cit. recall</TableHead>
                  <TableHead>Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((entry) => (
                  <FailureRow key={entry.question_id} entry={entry} />
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
