"use client";

import { useState } from "react";
import type {
  DisputePayload,
  PanelAnswerPayload,
  TraceEvent,
  TurnPayload,
  VerdictPayload,
  VerifyPayload,
} from "@/lib/types";

/**
 * The trace is the explanation. Every claim in the final answer has to be attributable, so this
 * shows the whole record: what each model said, what the gate decided and why, what evidence
 * came back with which sources, every debate turn including the steelman, and the rung taken.
 */

const SEAT_STYLE: Record<string, string> = {
  panel: "border-l-panel-line",
  referee: "border-l-referee-line",
  external: "border-l-external-line",
  code: "border-l-line",
};

const SEAT_OF: Record<string, keyof typeof SEAT_STYLE> = {
  "panel.answer": "panel",
  "panel.dropout": "panel",
  "debate.turn": "panel",
  "compare.verdict": "referee",
  "normalize.applied": "referee",
  "verify.result": "external",
  "dispute.opened": "code",
  "dispute.closed": "code",
  "cluster.converged": "code",
  "ladder.rung": "code",
  "stage.entered": "code",
  "run.started": "code",
  "run.final": "code",
  "run.error": "code",
  "model.call": "code",
};

function Row({ event, children }: { event: TraceEvent; children: React.ReactNode }) {
  return (
    <li
      className={`card border-l-2 p-3 ${SEAT_STYLE[SEAT_OF[event.type] ?? "code"]}`}
    >
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-[0.6rem] text-muted">{String(event.seq).padStart(2, "0")}</span>
        <span className="font-mono text-[0.68rem] font-semibold">{event.type}</span>
      </div>
      <div className="mt-1.5 text-sm">{children}</div>
    </li>
  );
}

function Collapse({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button
        onClick={() => setOpen(!open)}
        className="font-mono text-[0.65rem] text-muted underline decoration-dotted hover:text-ink"
      >
        {open ? "hide" : "show"} {title}
      </button>
      {open && <div className="mt-1.5 whitespace-pre-wrap text-[0.8rem] text-muted">{children}</div>}
    </div>
  );
}

export function TraceViewer({ events }: { events: TraceEvent[] }) {
  const [showAccounting, setShowAccounting] = useState(false);

  const visible = events.filter(
    (e) =>
      e.type !== "stage.entered" &&
      e.type !== "run.final" &&
      (showAccounting || e.type !== "model.call"),
  );

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="label">Trace</span>
        <button
          onClick={() => setShowAccounting(!showAccounting)}
          className="font-mono text-[0.65rem] text-muted underline decoration-dotted hover:text-ink"
        >
          {showAccounting ? "hide" : "show"} per-call accounting
        </button>
      </div>

      <ul className="flex flex-col gap-2">
        {visible.map((event) => {
          const p = event.payload;
          switch (event.type) {
            case "run.started":
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs">
                    {(p.models as string[]).join(", ")} · mode {String(p.mode)}
                  </span>
                  {Array.isArray(p.warnings) && (p.warnings as string[]).length > 0 && (
                    <ul className="mt-1.5 flex flex-col gap-1 text-xs text-alarm">
                      {(p.warnings as string[]).map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  )}
                </Row>
              );

            case "panel.answer": {
              const a = p as unknown as PanelAnswerPayload;
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs">{a.model}</span>
                  {a.normalized && (
                    <span className="ml-2 font-mono text-[0.6rem] text-alarm">
                      record recovered by normalizer
                    </span>
                  )}
                  <ul className="mt-1.5 flex flex-col gap-0.5 text-xs">
                    {a.key_claims.map((claim, i) => (
                      <li key={i} className="text-muted">
                        · {claim}
                      </li>
                    ))}
                  </ul>
                  {a.assumptions.length > 0 && (
                    <p className="mt-1.5 text-xs text-muted">
                      <span className="font-mono text-[0.6rem]">ASSUMED</span>{" "}
                      {a.assumptions.join("; ")}
                    </p>
                  )}
                  {a.expected_consensus && (
                    <p className="mt-1 text-xs text-muted">
                      <span className="font-mono text-[0.6rem]">PREDICTED</span>{" "}
                      {a.expected_consensus}
                    </p>
                  )}
                  <Collapse title="full answer">{a.answer}</Collapse>
                </Row>
              );
            }

            case "panel.dropout":
              return (
                <Row key={event.seq} event={event}>
                  <span className="text-alarm">
                    {String(p.model)} — {String(p.reason)}. Recorded as a dropout, not a stance.
                  </span>
                </Row>
              );

            case "compare.verdict": {
              const v = p as unknown as VerdictPayload;
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs font-semibold uppercase">{v.verdict}</span>
                  {v.unstable && (
                    <span className="ml-2 font-mono text-[0.6rem] text-alarm">
                      order-reversed re-run disagreed
                    </span>
                  )}
                  <p className="mt-1.5 text-xs text-muted">{v.justification}</p>
                  <ul className="mt-2 flex flex-col gap-1 text-xs">
                    {v.stances.map((s) => (
                      <li key={s.id}>
                        <span className="font-mono text-[0.65rem]">{s.id}</span> {s.summary}
                        <span className="ml-1 font-mono text-[0.6rem] text-muted">
                          [{s.members.join(", ")}]
                        </span>
                      </li>
                    ))}
                  </ul>
                </Row>
              );
            }

            case "dispute.opened": {
              const d = p as unknown as DisputePayload;
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-[0.65rem] uppercase text-muted">{d.type}</span>
                  <p className="mt-0.5">{d.question}</p>
                  <p className="mt-1.5 text-xs text-muted">
                    <span className="font-mono text-[0.6rem]">IMPACT</span> {d.decision_impact}
                  </p>
                  {d.search_query && (
                    <p className="mt-1 font-mono text-[0.65rem] text-muted">
                      query: {d.search_query}
                    </p>
                  )}
                </Row>
              );
            }

            case "verify.result": {
              const v = p as unknown as VerifyPayload;
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs font-semibold">{v.outcome}</span>
                  {v.winning_stance && (
                    <span className="ml-2 font-mono text-[0.65rem] text-muted">
                      → {v.winning_stance}
                    </span>
                  )}
                  <p className="mt-1.5 text-xs text-muted">{v.summary}</p>
                  {v.citations.length > 0 && (
                    <ul className="mt-2 flex flex-col gap-1 text-xs">
                      {v.citations.map((c, i) => (
                        <li key={i}>
                          <a
                            href={c.url}
                            target="_blank"
                            rel="noreferrer"
                            className={`underline decoration-dotted ${
                              v.supporting_urls.includes(c.url) ? "text-external" : "text-muted"
                            }`}
                          >
                            {c.title || c.url}
                          </a>
                          {v.supporting_urls.includes(c.url) && (
                            <span className="ml-1 font-mono text-[0.55rem] text-external">
                              carries the verdict
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </Row>
              );
            }

            case "debate.turn": {
              const t = p as unknown as TurnPayload;
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs">
                    round {t.round} · {t.stance_id}
                  </span>
                  <span className="ml-2 font-mono text-[0.6rem] text-muted">{t.model}</span>
                  {t.parse_degraded && (
                    <span className="ml-2 font-mono text-[0.6rem] text-alarm">
                      unparseable → held to DEFEND
                    </span>
                  )}
                  <ul className="mt-1.5 flex flex-col gap-1 text-xs">
                    {t.actions.map((a, i) => (
                      <li key={i}>
                        <span className="font-mono text-[0.65rem] font-semibold uppercase">
                          {a.action}
                        </span>{" "}
                        vs {a.against_stance}
                        {a.because && <span className="text-muted"> — {a.because}</span>}
                        {a.withdrawn_claim && (
                          <span className="text-muted"> (withdrew: {a.withdrawn_claim})</span>
                        )}
                      </li>
                    ))}
                  </ul>
                  {t.steelman && <Collapse title="steelman">{t.steelman}</Collapse>}
                  {t.response && <Collapse title="response">{t.response}</Collapse>}
                </Row>
              );
            }

            case "dispute.closed":
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs">
                    {String(p.dispute_id)} · {String(p.mechanism)} ·{" "}
                    {p.resolved ? "resolved" : "unresolved"}
                    {p.winning_stance ? ` → ${String(p.winning_stance)}` : ""}
                  </span>
                  {p.note ? <p className="mt-1 text-xs text-muted">{String(p.note)}</p> : null}
                </Row>
              );

            case "ladder.rung":
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-xs">
                    rung {String(p.rung)} · {String(p.label)} · {String(p.confidence)}
                  </span>
                  {p.tie_break_reason ? (
                    <p className="mt-1 text-xs text-muted">
                      tie-break: {String(p.tie_break_reason)}
                    </p>
                  ) : null}
                </Row>
              );

            case "model.call":
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-[0.68rem] text-muted">
                    {String(p.role)} · {String(p.slug)} · via {String(p.upstream_provider)} ·{" "}
                    {String(p.prompt_tokens)}+{String(p.completion_tokens)} tok · $
                    {((Number(p.cost_micros) || 0) / 1_000_000).toFixed(5)}
                    {p.routing_unpinned ? " · routed unpinned" : ""}
                  </span>
                </Row>
              );

            default:
              return (
                <Row key={event.seq} event={event}>
                  <span className="font-mono text-[0.68rem] text-muted">
                    {JSON.stringify(p).slice(0, 220)}
                  </span>
                </Row>
              );
          }
        })}
      </ul>
    </section>
  );
}
