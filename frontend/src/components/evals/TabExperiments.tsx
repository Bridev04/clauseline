"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchExperiments, ExperimentRun } from "@/lib/api";

function Delta({ value }: { value: number | undefined }) {
  if (value === undefined || value === null) return <span className="text-zinc-400">—</span>;
  const pct = (value * 100).toFixed(1);
  if (value > 0.001)
    return <span className="text-emerald-600 font-medium">+{pct}%</span>;
  if (value < -0.001)
    return <span className="text-red-500 font-medium">{pct}%</span>;
  return <span className="text-zinc-400">±0.0%</span>;
}

function shortRunId(runId: string): string {
  // run_2026-05-24T12-34-56Z → #1 label assigned by index, but show last 8 chars
  return runId.slice(-8);
}

export function TabExperiments() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["experiments"],
    queryFn: fetchExperiments,
  });

  if (isLoading) return <p className="text-zinc-500 text-sm">Loading experiments…</p>;
  if (error || !data)
    return (
      <p className="text-sm text-red-500">
        Could not load experiments. Run the eval harness to generate run data.
      </p>
    );

  if (data.length === 0)
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50 p-8 text-center">
        <p className="text-zinc-500 text-sm font-medium">No experiment runs yet</p>
        <p className="text-zinc-400 text-xs mt-1">
          Run{" "}
          <code className="font-mono bg-zinc-100 px-1 rounded">
            uv run python ../evals/scripts/run_eval.py
          </code>{" "}
          at least once to populate this timeline.
        </p>
      </div>
    );

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  const chartData = data.map((run: ExperimentRun, i: number) => ({
    label: `Run ${i + 1}`,
    "Pass rate": +(run.pass_rate * 100).toFixed(1),
    "Recall@8": +(run.recall_at_8 * 100).toFixed(1),
    "MRR@8": +(run.mrr_at_8 * 100).toFixed(1),
    "Citation P": +(run.containment_precision * 100).toFixed(1),
  }));

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Metric trend across runs</CardTitle>
          <p className="text-xs text-zinc-500">{data.length} run{data.length !== 1 ? "s" : ""}</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => (typeof v === "number" ? `${v}%` : v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="Pass rate" stroke="#3f3f46" strokeWidth={2} dot />
              <Line type="monotone" dataKey="Recall@8" stroke="#71717a" strokeWidth={2} dot />
              <Line type="monotone" dataKey="MRR@8" stroke="#a1a1aa" strokeWidth={2} dot />
              <Line type="monotone" dataKey="Citation P" stroke="#d4d4d8" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run history</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100 text-zinc-500 text-xs">
                  <th className="px-4 py-2 text-left font-medium">Run</th>
                  <th className="px-4 py-2 text-left font-medium">Started</th>
                  <th className="px-4 py-2 text-right font-medium">Qs</th>
                  <th className="px-4 py-2 text-right font-medium">Pass</th>
                  <th className="px-4 py-2 text-right font-medium">Δ</th>
                  <th className="px-4 py-2 text-right font-medium">Recall@8</th>
                  <th className="px-4 py-2 text-right font-medium">Δ</th>
                  <th className="px-4 py-2 text-right font-medium">MRR@8</th>
                  <th className="px-4 py-2 text-right font-medium">Δ</th>
                  <th className="px-4 py-2 text-right font-medium">Cite P</th>
                  <th className="px-4 py-2 text-right font-medium">Δ</th>
                </tr>
              </thead>
              <tbody>
                {data.map((run: ExperimentRun, i: number) => (
                  <tr key={run.run_id} className="border-b border-zinc-50 hover:bg-zinc-50">
                    <td className="px-4 py-2 font-mono text-xs text-zinc-400" title={run.run_id}>
                      Run {i + 1} <span className="text-zinc-300">·{shortRunId(run.run_id)}</span>
                    </td>
                    <td className="px-4 py-2 text-zinc-500 text-xs whitespace-nowrap">
                      {new Date(run.started_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{run.question_count}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{pct(run.pass_rate)}</td>
                    <td className="px-4 py-2 text-right">
                      <Delta value={run.delta?.pass_rate} />
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{pct(run.recall_at_8)}</td>
                    <td className="px-4 py-2 text-right">
                      <Delta value={run.delta?.recall_at_8} />
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{run.mrr_at_8.toFixed(3)}</td>
                    <td className="px-4 py-2 text-right">
                      <Delta value={run.delta?.mrr_at_8} />
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {pct(run.containment_precision)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Delta value={run.delta?.containment_precision} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
