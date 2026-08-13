"use client";

import { useEffect, useRef, useState } from "react";
import type { FinalAnswer, ModelInfo, RunSummary, Stage, TraceEvent } from "./types";

export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function fetchModels(): Promise<ModelInfo[]> {
  const res = await fetch(`${API}/models`, { cache: "no-store" });
  if (!res.ok) throw new Error(`models: ${res.status}`);
  return res.json();
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const res = await fetch(`${API}/runs`, { cache: "no-store" });
  if (!res.ok) throw new Error(`runs: ${res.status}`);
  return res.json();
}

export async function startRun(body: {
  task: string;
  context?: string | null;
  models: string[];
  mode: string;
}): Promise<{ run_id: string; warnings: string[] }> {
  const res = await fetch(`${API}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail ?? `run failed: ${res.status}`);
  return data;
}

export interface RunState {
  events: TraceEvent[];
  stage: Stage | null;
  final: FinalAnswer | null;
  error: string | null;
  live: boolean;
}

/**
 * Subscribes to a run's event tape.
 *
 * The stream replays the tape from the beginning before switching to live events, so opening a
 * finished run and watching one live produce the identical timeline — there is no separate
 * "history" code path that could drift from what viewers saw happen.
 */
export function useRunStream(runId: string): RunState {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [live, setLive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seen = useRef<Set<number>>(new Set());

  useEffect(() => {
    const source = new EventSource(`${API}/runs/${runId}/stream`);

    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as TraceEvent;
      if (seen.current.has(event.seq)) return;
      seen.current.add(event.seq);
      setEvents((prev) => [...prev, event].sort((a, b) => a.seq - b.seq));
      if (event.type === "run.final" || event.type === "run.error") {
        setLive(false);
        source.close();
      }
    };

    source.onerror = () => {
      // The server closes the stream when a run ends; that surfaces here as an error even
      // though nothing failed. Only report it if we never reached a terminal event.
      setLive(false);
      source.close();
    };

    return () => source.close();
  }, [runId]);

  const final =
    (events.find((e) => e.type === "run.final")?.payload as unknown as FinalAnswer) ?? null;
  const failure = events.find((e) => e.type === "run.error");
  const stage =
    ([...events].reverse().find((e) => e.type === "stage.entered")?.payload?.stage as Stage) ??
    null;

  useEffect(() => {
    if (failure) setError(String(failure.payload.detail ?? "run failed"));
  }, [failure]);

  return { events, stage, final, error, live };
}
