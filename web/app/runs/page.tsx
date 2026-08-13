"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

export default function History() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRuns().then(setRuns).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <h1 className="text-xl font-semibold tracking-tight">Past deliberations</h1>
      {error && <p className="text-sm text-alarm">{error}</p>}
      {runs.length === 0 && !error && <p className="text-sm text-muted">Nothing yet.</p>}
      <ul className="flex flex-col gap-2">
        {runs.map((run) => (
          <li key={run._id}>
            <Link
              href={`/runs/${run._id}`}
              className="card flex flex-col gap-1 p-3 hover:border-referee-line"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="line-clamp-1 text-sm">{run.request?.task}</span>
                <span className="shrink-0 font-mono text-[0.65rem] text-muted">
                  {run.label ?? run.status}
                  {run.confidence ? ` · ${run.confidence}` : ""}
                </span>
              </div>
              <div className="flex gap-4 font-mono text-[0.6rem] text-muted">
                <span>{run.request?.models?.length ?? 0} models</span>
                {run.calls ? <span>{run.calls} calls</span> : null}
                {run.cost_micros ? (
                  <span>${(run.cost_micros / 1_000_000).toFixed(4)}</span>
                ) : null}
                <span>{new Date(run.created_at).toLocaleString()}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
