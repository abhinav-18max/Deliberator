/**
 * The three architecture figures, hand-authored SVG.
 *
 * Each one depicts a mechanism rather than naming a component: where a request goes, what is
 * decided in code versus by a model, and which paths are skipped when the gate stays quiet.
 * The colour encoding matches the trace viewer, so the same vocabulary reads across both.
 */

export function Legend() {
  const items: [string, string][] = [
    ["b-code", "deterministic code"],
    ["b-panel", "panel model call (user-selected)"],
    ["b-ref", "referee model call (system-owned, off-panel)"],
    ["b-ext", "external retrieval"],
  ];
  return (
    <ul className="flex flex-wrap gap-x-6 gap-y-1.5">
      {items.map(([cls, label]) => (
        <li key={cls} className="flex items-center gap-2 font-mono text-[0.65rem] text-muted">
          <svg width="22" height="12" aria-hidden="true">
            <rect x="0.5" y="0.5" width="21" height="11" rx="3" className={cls} />
          </svg>
          {label}
        </li>
      ))}
      <li className="font-mono text-[0.65rem] text-muted">dashed box = conditional or mode-gated</li>
    </ul>
  );
}

export function PipelineFigure() {
  return (
    <svg
      viewBox="0 0 1200 520"
      role="img"
      aria-label="End-to-end pipeline: a code orchestrator drives guard, parallel fan-out to panel models, a comparator gate that can bypass straight to synthesis, a resolver routing disputes to verification, branching or debate, and a synthesizer producing one labelled answer. Every step appends to an append-only trace."
      style={{ width: "100%", minWidth: 760, maxWidth: 1200 }}
    >
      <defs>
        <marker id="ar-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="head" />
        </marker>
        <marker id="ar-v" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="head-v" />
        </marker>
      </defs>

      <rect x="24" y="18" width="1152" height="48" rx="6" className="b-band" />
      <text className="ttl" x="40" y="40">ORCHESTRATOR</text>
      <text className="sub" x="40" y="56">plain code — sequencing, gating, convergence checks, ladder, termination</text>
      <text className="lbl" x="1160" y="40" textAnchor="end">config: mode · max_rounds · role registry</text>
      <text className="lbl" x="1160" y="56" textAnchor="end">no LLM in the control path</text>

      <g className="wire-dash" markerEnd="url(#ar-a)">
        <path d="M80 66 V96" /><path d="M262 66 V96" /><path d="M471 66 V96" />
        <path d="M710 66 V96" /><path d="M949 66 V96" />
      </g>
      <text className="lbl" x="88" y="88">calls · advances</text>

      <path className="wire" d="M500 186 V124 H920 V186" markerEnd="url(#ar-a)" />
      <text className="lbl" x="710" y="116" textAnchor="middle">verdict NONE / SURFACE → skip resolve</text>

      <rect x="24" y="194" width="98" height="88" rx="5" className="b-code" />
      <text className="ttl" x="73" y="218" textAnchor="middle">0 · GUARD</text>
      <text className="sub" x="73" y="238" textAnchor="middle">fence as data</text>
      <text className="sub" x="73" y="254" textAnchor="middle">verbatim task</text>
      <text className="sub" x="73" y="270" textAnchor="middle">never rewrite</text>

      <rect x="168" y="163" width="188" height="150" rx="5" className="b-code" />
      <text className="ttl" x="178" y="183">1 · FAN-OUT</text>
      <text className="sub" x="346" y="183" textAnchor="end">parallel</text>
      <rect x="180" y="194" width="164" height="26" rx="4" className="b-panel" />
      <text className="lbl-ink" x="262" y="211" textAnchor="middle">panel model A</text>
      <rect x="180" y="226" width="164" height="26" rx="4" className="b-panel" />
      <text className="lbl-ink" x="262" y="243" textAnchor="middle">panel model B</text>
      <rect x="180" y="258" width="164" height="26" rx="4" className="b-panel" />
      <text className="lbl-ink" x="262" y="275" textAnchor="middle">panel model C</text>
      <text className="lbl" x="262" y="300" textAnchor="middle">no model sees another</text>

      <rect x="402" y="186" width="138" height="104" rx="5" className="b-ref" />
      <text className="ttl" x="471" y="208" textAnchor="middle">2 · COMPARE</text>
      <text className="sub" x="471" y="228" textAnchor="middle">cluster → stances</text>
      <text className="sub" x="471" y="244" textAnchor="middle">verdict + typed</text>
      <text className="sub" x="471" y="260" textAnchor="middle">disputes</text>
      <text className="lbl hue-t" x="471" y="279" textAnchor="middle">the gate · temp 0</text>

      <rect x="586" y="150" width="248" height="176" rx="5" className="b-code" />
      <text className="ttl" x="596" y="172">3 · RESOLVE</text>
      <text className="sub" x="824" y="172" textAnchor="end">route by type</text>
      <rect x="596" y="186" width="228" height="38" rx="4" className="b-panel" />
      <text className="lbl" x="608" y="201">approach</text>
      <text className="lbl-ink" x="608" y="216">→ DEBATE · ≤ 2 rounds</text>
      <rect x="596" y="228" width="228" height="38" rx="4" className="b-solid" />
      <text className="lbl" x="608" y="243">interpretation</text>
      <text className="lbl-ink" x="608" y="258">→ BRANCH · no debate, no winner</text>
      <rect x="596" y="270" width="228" height="38" rx="4" className="b-ref" />
      <text className="lbl" x="608" y="285">factual · checkable</text>
      <text className="lbl-ink" x="608" y="300">→ VERIFY · evidence beats rhetoric</text>

      <rect x="880" y="186" width="138" height="104" rx="5" className="b-ref" />
      <text className="ttl" x="949" y="208" textAnchor="middle">4 · FINALIZE</text>
      <text className="sub" x="949" y="228" textAnchor="middle">walk the ladder</text>
      <text className="sub" x="949" y="244" textAnchor="middle">compose, never</text>
      <text className="sub" x="949" y="260" textAnchor="middle">blend or invent</text>
      <text className="lbl hue-t" x="949" y="279" textAnchor="middle">off-panel · pinned</text>

      <rect x="1064" y="194" width="112" height="88" rx="5" className="b-out" />
      <text className="ttl" x="1120" y="217" textAnchor="middle">ANSWER</text>
      <text className="sub" x="1120" y="236" textAnchor="middle">+ resolution</text>
      <text className="sub" x="1120" y="252" textAnchor="middle">+ confidence</text>
      <text className="sub" x="1120" y="268" textAnchor="middle">+ caveats</text>

      <g className="wire" markerEnd="url(#ar-a)">
        <path d="M122 238 H164" />
        <path d="M356 238 H398" />
        <path d="M540 238 H582" />
        <path d="M834 238 H876" />
        <path d="M1018 238 H1060" />
      </g>
      <text className="lbl" x="143" y="230" textAnchor="middle">×N</text>
      <text className="lbl" x="377" y="230" textAnchor="middle">answers</text>
      <text className="lbl" x="561" y="230" textAnchor="middle">disputes</text>
      <text className="lbl" x="855" y="230" textAnchor="middle">outcomes</text>
      <text className="lbl" x="1039" y="230" textAnchor="middle">one</text>

      <rect x="168" y="356" width="188" height="48" rx="5" className="b-ref-d" />
      <text className="ttl" x="262" y="378" textAnchor="middle">NORMALIZER</text>
      <text className="sub" x="262" y="394" textAnchor="middle">only on JSON failure</text>
      <path className="wire-dash" d="M262 313 V352" markerEnd="url(#ar-a)" markerStart="url(#ar-a)" />
      <text className="lbl" x="272" y="338">prose → record</text>

      <rect x="402" y="356" width="180" height="48" rx="5" className="b-ref-d" />
      <text className="ttl" x="492" y="378" textAnchor="middle">RED TEAM</text>
      <text className="sub" x="492" y="394" textAnchor="middle">rigorous · only on NONE</text>
      <path className="wire-dash" d="M492 356 V294" markerEnd="url(#ar-a)" />
      <text className="lbl" x="484" y="332" textAnchor="end">attack unanimity</text>

      <rect x="690" y="356" width="180" height="48" rx="5" className="b-ext" />
      <text className="ttl" x="780" y="378" textAnchor="middle">GROUNDING</text>
      <text className="sub" x="780" y="394" textAnchor="middle">gateway web search</text>
      <path className="wire-v" d="M780 308 V352" markerEnd="url(#ar-v)" markerStart="url(#ar-v)" />
      <text className="lbl hue-v" x="790" y="336">neutral query ⇄ cited spans</text>

      <rect x="24" y="440" width="1152" height="56" rx="6" className="b-solid" />
      <text className="ttl" x="40" y="464">TRACE · append-only</text>
      <text className="sub" x="40" y="482">per call: role · slug · upstream provider · prompt_version · tokens · cost · evidence artifact — replayable, and the eval harness runs off it</text>
      <text className="lbl" x="1160" y="464" textAnchor="end">the trace is the explanation</text>
      <g className="wire-faint" markerEnd="url(#ar-a)">
        <path d="M73 282 V436" /><path d="M200 313 V436" /><path d="M262 404 V436" />
        <path d="M440 290 V436" /><path d="M492 404 V436" /><path d="M620 326 V436" />
        <path d="M780 404 V436" /><path d="M949 290 V436" />
      </g>
      <text className="lbl" x="82" y="424">appends</text>
    </svg>
  );
}

export function DebateFigure() {
  return (
    <svg
      viewBox="0 0 1160 250"
      role="img"
      aria-label="Per-dispute debate machine: k stances each get one advocate, round one requires a steelman then a machine-readable action, a code convergence check either closes the dispute or re-clusters into round two, and a second check yields resolved or a legitimately unresolved outcome."
      style={{ width: "100%", minWidth: 720, maxWidth: 1160 }}
    >
      <defs>
        <marker id="ar-b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="head" />
        </marker>
      </defs>

      <rect x="24" y="78" width="96" height="64" rx="5" className="b-solid" />
      <text className="ttl" x="72" y="106" textAnchor="middle">k STANCES</text>
      <text className="sub" x="72" y="124" textAnchor="middle">1 advocate</text>

      <rect x="150" y="78" width="222" height="64" rx="5" className="b-panel" />
      <text className="ttl" x="261" y="100" textAnchor="middle">ROUND 1 · CONFRONT</text>
      <text className="sub" x="261" y="118" textAnchor="middle">steelman first, then respond</text>
      <text className="lbl" x="261" y="134" textAnchor="middle">DEFEND | REVISE | CONCEDE</text>

      <polygon points="392,110 440,70 488,110 440,150" className="b-code" />
      <text className="lbl-ink" x="440" y="108" textAnchor="middle">converged?</text>
      <text className="lbl" x="440" y="122" textAnchor="middle">code</text>

      <rect x="506" y="90" width="120" height="40" rx="5" className="b-code" />
      <text className="ttl" x="566" y="108" textAnchor="middle">RE-CLUSTER</text>
      <text className="lbl" x="566" y="123" textAnchor="middle">votes move</text>

      <rect x="646" y="78" width="210" height="64" rx="5" className="b-panel" />
      <text className="ttl" x="751" y="100" textAnchor="middle">ROUND 2 · REBUT</text>
      <text className="sub" x="751" y="118" textAnchor="middle">answer the rebuttal</text>
      <text className="lbl" x="751" y="134" textAnchor="middle">no restating your case</text>

      <polygon points="872,110 920,70 968,110 920,150" className="b-code" />
      <text className="lbl-ink" x="920" y="108" textAnchor="middle">still split?</text>
      <text className="lbl" x="920" y="122" textAnchor="middle">code</text>

      <rect x="1010" y="36" width="142" height="48" rx="5" className="b-out" />
      <text className="ttl" x="1081" y="58" textAnchor="middle">RESOLVED</text>
      <text className="sub" x="1081" y="74" textAnchor="middle">surviving position</text>

      <rect x="1010" y="136" width="142" height="48" rx="5" className="b-out" />
      <text className="ttl" x="1081" y="158" textAnchor="middle">UNRESOLVED</text>
      <text className="sub" x="1081" y="174" textAnchor="middle">legitimate outcome</text>

      <g className="wire" markerEnd="url(#ar-b)">
        <path d="M120 110 H146" />
        <path d="M372 110 H388" />
        <path d="M488 110 H502" />
        <path d="M626 110 H642" />
        <path d="M856 110 H868" />
        <path d="M440 70 V24 H1081 V32" />
        <path d="M968 110 L1006 66" />
        <path d="M968 110 L1006 154" />
      </g>
      <text className="lbl" x="495" y="102">no</text>
      <text className="lbl" x="760" y="16" textAnchor="middle">yes — concession or compatible merge closes it</text>
      <text className="lbl" x="978" y="80">no</text>
      <text className="lbl" x="978" y="146">yes</text>

      <text className="lbl" x="24" y="222">orchestrator composes every prompt · opponents anonymised · both sides challenged simultaneously · hard stop at max_rounds</text>
    </svg>
  );
}

const RUNGS: {
  indent: number;
  y: number;
  text: string;
  label: string;
  confidence: string;
  chip: string;
}[] = [
  { indent: 0, y: 36, text: "gate found no material dispute — the bypass", label: "unanimous", confidence: "high", chip: "c-high" },
  { indent: 20, y: 82, text: "1 · debate resolved it — someone conceded and said why", label: "debate-resolved", confidence: "high", chip: "c-high" },
  { indent: 40, y: 128, text: "2 · evidence settled it — cited spans attached", label: "verified", confidence: "high", chip: "c-high" },
  { indent: 60, y: 174, text: "3 · majority — counted only after argument", label: "majority (2/3)", confidence: "medium", chip: "c-med" },
  { indent: 80, y: 220, text: "4 · tie-break on visible evidence, reason published", label: "tie-break", confidence: "low", chip: "c-low" },
  { indent: 100, y: 266, text: "5 · floor — the default model's answer, alternative named", label: "floor", confidence: "low", chip: "c-low" },
];

export function LadderFigure() {
  return (
    <svg
      viewBox="0 0 1160 350"
      role="img"
      aria-label="Resolution ladder: six descending rungs from unanimous agreement through debate, verification, majority, tie-break and a floor, each mapped to a resolution label and a mechanically derived confidence level."
      style={{ width: "100%", minWidth: 700, maxWidth: 1160 }}
    >
      <defs>
        <marker id="ar-c" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" className="head" />
        </marker>
      </defs>

      <text className="lbl" x="40" y="22">rung — how the answer won</text>
      <text className="lbl" x="600" y="22">resolution label (the contract)</text>
      <text className="lbl" x="880" y="22">confidence (derived, never self-reported)</text>

      {RUNGS.map((rung) => {
        const x = 40 + rung.indent;
        return (
          <g key={rung.label}>
            <rect x={x} y={rung.y} width={580 - rung.indent} height="36" rx="4" className="b-solid" />
            <text className="lbl-ink" x={x + 14} y={rung.y + 23}>{rung.text}</text>
            <rect x="600" y={rung.y + 4} width="150" height="28" rx="4" className="c-chip" />
            <text className="lbl-ink" x="675" y={rung.y + 23} textAnchor="middle">{rung.label}</text>
            <rect x="880" y={rung.y + 4} width="70" height="28" rx="4" className={rung.chip} />
            <text className="lbl-ink" x="915" y={rung.y + 23} textAnchor="middle">{rung.confidence}</text>
          </g>
        );
      })}

      <g className="wire-faint" markerEnd="url(#ar-c)">
        <path d="M46 72 V78" /><path d="M66 118 V124" /><path d="M86 164 V170" />
        <path d="M106 210 V216" /><path d="M126 256 V262" />
      </g>

      <text className="lbl" x="40" y="326">descend only when the rung above does not apply · voting sits below argument · the ladder cannot exit empty</text>
    </svg>
  );
}
