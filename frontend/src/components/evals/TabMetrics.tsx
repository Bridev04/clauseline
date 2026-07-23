"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchEvalSummary } from "@/lib/api";

const BUCKET_LABELS: Record<string, string> = {
  A: "Single-chunk",
  B: "Multi-chunk",
  C: "Unanswerable",
};

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-zinc-500">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

export function TabMetrics() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["eval-summary"],
    queryFn: fetchEvalSummary,
  });

  if (isLoading) return <p className="text-zinc-500 text-sm">Loading metrics…</p>;
  if (error || !data)
    return (
      <p className="text-sm text-red-500">
        No eval results found. Run{" "}
        <code className="font-mono bg-zinc-100 px-1 rounded">
          uv run python ../evals/scripts/run_eval.py
        </code>{" "}
        first.
      </p>
    );

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  const chartData = data.per_bucket.map((b) => ({
    name: BUCKET_LABELS[b.bucket] ?? b.bucket,
    "Recall@8": +(b.recall_at_8 * 100).toFixed(1),
    "Containment P": +(b.containment_precision * 100).toFixed(1),
    "Containment R": +(b.containment_recall * 100).toFixed(1),
    "Pass rate": +(b.pass_rate * 100).toFixed(1),
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="Pass rate" value={pct(data.pass_rate)} />
        <MetricCard label="Recall@8" value={pct(data.recall_at_8)} />
        <MetricCard label="MRR@8" value={data.mrr_at_8.toFixed(3)} />
        <MetricCard label="Citation precision" value={pct(data.containment_precision)} />
        <MetricCard label="Citation recall" value={pct(data.containment_recall)} />
      </div>

      <p className="text-xs text-zinc-400">
        Latest run · {data.total_questions}-question hand-built golden set, 1 contract —
        directional, not a benchmark. Cross-run trend on the Experiments tab.
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Per-bucket breakdown</CardTitle>
          <p className="text-xs text-zinc-500">
            {data.total_questions} questions · {data.run_count} run
            {data.run_count !== 1 ? "s" : ""}
          </p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => (typeof v === "number" ? `${v}%` : v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Recall@8" fill="#3f3f46" />
              <Bar dataKey="Containment P" fill="#71717a" />
              <Bar dataKey="Containment R" fill="#a1a1aa" />
              <Bar dataKey="Pass rate" fill="#d4d4d8" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
