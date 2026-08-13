"use client";

import type { FinalAnswer } from "@/lib/types";

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "border-referee-line bg-referee-bg text-referee",
  medium: "border-panel-line bg-panel-bg text-panel",
  low: "border-alarm-line bg-alarm-bg text-alarm",
};

const HOW_IT_WON: Record<string, string> = {
  unanimous: "Every model reached the same conclusion; no material dispute was found.",
  "debate-resolved": "A dispute was argued and one side conceded, citing what changed its mind.",
  verified: "A disputed fact was checked against cited sources, and the evidence decided it.",
  majority: "Argument did not settle it, so the position held by the most models won.",
  "tie-break": "The panel split evenly, so the answer was chosen on visible evidence.",
  floor: "Nothing distinguished the positions, so the designated default model's answer stands.",
};

export function AnswerCard({ final }: { final: FinalAnswer }) {
  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded border border-ink px-2 py-0.5 font-mono text-xs font-semibold">
          {final.resolution}
        </span>
        <span
          className={`rounded border px-2 py-0.5 font-mono text-xs ${CONFIDENCE_STYLE[final.confidence]}`}
        >
          confidence: {final.confidence}
        </span>
        {final.dissent && (
          <span className="rounded border border-line px-2 py-0.5 font-mono text-xs text-muted">
            {final.dissent} dissent
          </span>
        )}
        {!final.gate_validated && (
          <span className="rounded border border-alarm-line px-2 py-0.5 font-mono text-xs text-alarm">
            gate: unvalidated
          </span>
        )}
      </div>

      <p className="mt-2 text-xs text-muted">{HOW_IT_WON[final.label]}</p>

      <div className="mt-4 whitespace-pre-wrap text-[0.92rem] leading-relaxed">
        {final.final_answer}
      </div>

      {final.tie_break_reason && (
        <p className="mt-4 text-xs text-muted">
          Tie broken on: {final.tie_break_reason}.
        </p>
      )}

      {final.caveats.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <span className="label">Caveats</span>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm text-muted">
            {final.caveats.map((caveat, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-muted/60">—</span>
                <span>{caveat}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-3 font-mono text-[0.65rem] text-muted">
        <span>{final.calls} calls</span>
        <span>${(final.cost_micros / 1_000_000).toFixed(4)}</span>
        <span>{(final.duration_ms / 1000).toFixed(1)}s</span>
        <span>panel: {final.panel.join(", ")}</span>
        {final.referees
          .filter((r) => ["comparator", "synthesizer", "verifier"].includes(r.role))
          .map((r) => (
            <span key={r.role}>
              {r.role}: {r.slug}
              {r.off_panel ? "" : " (on panel)"}
            </span>
          ))}
      </div>
    </section>
  );
}
