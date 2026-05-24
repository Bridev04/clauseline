"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { QAResponse } from "@/lib/api";

const CONFIDENCE_BADGE: Record<string, string> = {
  high: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-orange-100 text-orange-800",
  none: "bg-zinc-100 text-zinc-500",
};

export function TrustPanel({ result }: { result: QAResponse }) {
  const groundedCount = result.citations.filter((c) => c.is_grounded).length;
  const badgeCls = CONFIDENCE_BADGE[result.confidence] ?? CONFIDENCE_BADGE.low;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2 flex flex-row items-start justify-between gap-4">
          <CardTitle className="text-base">Answer</CardTitle>
          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${badgeCls}`}>
            {result.confidence} confidence
          </span>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed">{result.answer}</p>
        </CardContent>
      </Card>

      {result.citations.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Evidence{" "}
              <span className="text-xs text-zinc-400 font-normal">
                ({groundedCount}/{result.citations.length} grounded)
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {result.citations.map((c, i) => (
              <div
                key={i}
                className={`rounded border p-3 text-sm ${
                  c.is_grounded
                    ? "border-green-200 bg-green-50"
                    : "border-zinc-200 bg-zinc-50 opacity-60"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs text-zinc-400">
                    page {c.page} · chunk {c.chunk_id.slice(0, 8)}…
                  </span>
                  {!c.is_grounded && (
                    <span className="text-xs text-orange-500 font-medium">
                      not grounded
                    </span>
                  )}
                </div>
                <blockquote className="italic text-zinc-700">&ldquo;{c.quoted_text}&rdquo;</blockquote>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-zinc-400">
        Retrieved {result.retrieved_count} chunk{result.retrieved_count !== 1 ? "s" : ""}
        {result.trace_id && (
          <> · trace <span className="font-mono">{result.trace_id}</span></>
        )}
      </p>
    </div>
  );
}
