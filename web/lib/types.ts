/**
 * Mirrors the backend contracts for the fields this UI consumes.
 *
 * Hand-written rather than generated so `npm run build` works without the API running;
 * `npm run types:gen` writes the full generated surface to lib/api-types.ts when you want to
 * diff this against the real OpenAPI schema.
 */

export type EventType =
  | "run.started"
  | "stage.entered"
  | "panel.answer"
  | "panel.dropout"
  | "normalize.applied"
  | "compare.verdict"
  | "dispute.opened"
  | "verify.result"
  | "debate.turn"
  | "cluster.converged"
  | "dispute.closed"
  | "ladder.rung"
  | "model.call"
  | "run.final"
  | "run.error";

export type Stage = "guard" | "fanout" | "compare" | "resolve" | "finalize";

export interface TraceEvent {
  run_id: string;
  seq: number;
  type: EventType;
  ts: string;
  // Payload shape varies by event type; the viewer narrows where it needs to.
  payload: Record<string, unknown>;
}

export interface ModelInfo {
  slug: string;
  family: string;
  in_default: boolean;
  structured_outputs: boolean | null;
  web_search: boolean | null;
  context_length: number | null;
}

export interface RoleAssignment {
  role: string;
  slug: string;
  prompt_version: string;
  off_panel: boolean;
}

export interface FinalAnswer {
  final_answer: string;
  label: "unanimous" | "debate-resolved" | "verified" | "majority" | "tie-break" | "floor";
  resolution: string;
  confidence: "high" | "medium" | "low";
  caveats: string[];
  rung: number;
  tie_break_reason: string | null;
  unresolved_disputes: string[];
  dissent: "informed" | "oblivious" | "unclassifiable" | null;
  panel: string[];
  referees: RoleAssignment[];
  gate_validated: boolean;
  calls: number;
  cost_micros: number;
  duration_ms: number;
}

export interface PanelAnswerPayload {
  model: string;
  answer: string;
  key_claims: string[];
  assumptions: string[];
  expected_consensus: string | null;
  normalized: boolean;
  cost_micros: number;
}

export interface StancePayload {
  id: string;
  summary: string;
  members: string[];
  strongest: string;
}

export interface VerdictPayload {
  verdict: "none" | "surface" | "material";
  justification: string;
  unstable: boolean;
  stances: StancePayload[];
  dispute_count: number;
}

export interface DisputePayload {
  id: string;
  type: "factual" | "interpretation" | "approach";
  question: string;
  decision_impact: string;
  positions: Record<string, string>;
  search_query: string | null;
}

export interface CitationPayload {
  url: string;
  title: string;
  snippet: string;
}

export interface VerifyPayload {
  dispute_id: string;
  outcome: "supports" | "conflicting" | "unverifiable";
  winning_stance: string | null;
  summary: string;
  queries: string[];
  citations: CitationPayload[];
  supporting_urls: string[];
}

export interface TurnPayload {
  dispute_id: string;
  round: number;
  stance_id: string;
  model: string;
  steelman: string;
  response: string;
  actions: { against_stance: string; action: string; because: string; withdrawn_claim: string | null }[];
  parse_degraded: boolean;
}

export interface RunSummary {
  _id: string;
  status: "running" | "complete" | "failed";
  stage: Stage | null;
  created_at: string;
  label?: string;
  confidence?: string;
  calls?: number;
  cost_micros?: number;
  request: { task: string; models: string[]; mode: string };
}

export const STAGES: Stage[] = ["guard", "fanout", "compare", "resolve", "finalize"];
