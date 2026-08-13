"use client";

import { STAGES, type Stage, type TraceEvent } from "@/lib/types";

const LABELS: Record<Stage, string> = {
  guard: "0 · guard",
  fanout: "1 · answer",
  compare: "2 · compare",
  resolve: "3 · resolve",
  finalize: "4 · finalize",
};

/**
 * The pipeline is sequential and therefore slower than a single call. The interface pays that
 * back by making the deliberation itself visible — a stage that is running says what it is
 * doing, so the wait is the product rather than a spinner in front of it.
 */
export function StageTimeline({
  events,
  current,
  live,
  finished,
}: {
  events: TraceEvent[];
  current: Stage | null;
  live: boolean;
  finished: boolean;
}) {
  const reached = new Set(
    events.filter((e) => e.type === "stage.entered").map((e) => e.payload.stage as Stage),
  );
  const answers = events.filter((e) => e.type === "panel.answer").length;
  const dropouts = events.filter((e) => e.type === "panel.dropout").length;
  const verdict = events.find((e) => e.type === "compare.verdict")?.payload;
  const disputes = events.filter((e) => e.type === "dispute.opened").length;
  const turns = events.filter((e) => e.type === "debate.turn").length;
  const verifications = events.filter((e) => e.type === "verify.result").length;

  const detail: Record<Stage, string> = {
    guard: "fenced verbatim",
    fanout: `${answers} answered${dropouts ? `, ${dropouts} dropped` : ""}`,
    compare: verdict ? `${String(verdict.verdict)} · ${Number(verdict.dispute_count)} dispute(s)` : "",
    resolve: [
      verifications ? `${verifications} checked` : "",
      turns ? `${turns} debate turn(s)` : "",
      disputes && !verifications && !turns ? `${disputes} routed` : "",
    ]
      .filter(Boolean)
      .join(" · "),
    finalize: "",
  };

  return (
    <ol className="flex flex-wrap gap-2">
      {STAGES.map((stage) => {
        const active = live && current === stage;
        const done = reached.has(stage) && !active;
        const skipped = !reached.has(stage);
        return (
          <li
            key={stage}
            className={`flex min-w-[7.5rem] flex-1 flex-col rounded border px-3 py-2 ${
              active
                ? "border-referee-line bg-referee-bg"
                : done
                  ? "border-line bg-surface"
                  : "border-dashed border-line bg-transparent"
            }`}
          >
            <span
              className={`font-mono text-[0.65rem] tracking-wide ${
                skipped ? "text-muted/50" : "text-ink"
              }`}
            >
              {LABELS[stage]}
              {active && <span className="ml-1 animate-pulse text-referee">●</span>}
            </span>
            <span className="mt-0.5 text-[0.7rem] text-muted">
              {skipped && stage === "resolve" && finished
                ? "skipped — no material dispute"
                : detail[stage]}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
