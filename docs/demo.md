# Demonstration

Five real deliberations, run against live models through the HTTP API. The full tapes are in
`docs/demo/*.json` — every panel answer, the gate's justification, each debate turn with its
steelman, the citations, and the rung taken.

```bash
cd api && uv run python -m app.demo.seed   # load the tapes into Mongo (no API key needed)
make web                                   # then open http://localhost:3000/runs
```

Seeding validates each tape on the way in: a fixture whose label its own events do not support is
rejected rather than shown, because the product's central claim is that labels are checkable.

Panel for all five: `openai/gpt-5.2`, `deepseek/deepseek-v3.2`, `qwen/qwen3-max` — three distinct
families, all off-panel from every referee seat. Referees: comparator `google/gemini-2.5-pro`,
verifier `anthropic/claude-haiku-4.5` (gateway retrieval), synthesizer `anthropic/claude-sonnet-5`,
red team `x-ai/grok-4.6`.

| # | Task | Mode | Result | Calls | Cost | What it demonstrates |
|---|---|---|---|---|---|---|
| 1 | `git reset --hard HEAD~1` semantics | fast | **verified / high** (rung 2) | 7 | $0.0785 | Evidence beating a head-count |
| 2 | Monorepo or separate repos, 6 engineers | fast | **unanimous / high** (rung 0) | 6 | $0.0591 | The gate's payoff |
| 3 | 40-minute CI suite, what first | fast | **majority (2/3) / medium** (rung 3) | 9 | $0.0629 | A debate that honestly failed |
| 4 | $5,000 observability budget | fast | **tie-break / low** (rung 4) | 9 | $0.1118 | Ambiguity branched, then an even split |
| 5 | Same as #2 | **rigorous** | **unanimous / medium** (rung 0) | 8 | $0.1011 | An attack landing on a consensus |

> **On the cost column.** These are the real reported figures with one honest asterisk: some
> providers return no cost at all (Gemini through OpenRouter reports zero), so those calls are
> estimated from catalogue pricing × tokens and marked `cost_estimated` in the trace. Before that
> fix the comparator appeared free, which understated a full run by roughly half — it is in fact
> the most expensive seat, reading every answer at ~3,500 prompt tokens per call.

---

## 1. Evidence beats the majority — `verified`

`docs/demo/01KZX5ACR26PF4BDZTZFHWJFC7.json`

Two models said a hard reset destroys everything uncommitted, including untracked files. One said
untracked files survive. The gate returned **material**, clustered 1-against-2, and typed the
disagreement `factual` with a search query attached.

Verification ran two framings, came back `supports` with 10 citations — and backed the
**single-model minority**. The answer states that untracked files are untouched, which is what
git's own documentation says and what two of three models got wrong.

The label is `verified` rather than `majority`, so a reader knows the answer won on sources rather
than on a show of hands. Dissent was classified **oblivious**: the two models that got it wrong
also expected everyone to agree with them.

> **A bug this case exposed.** An earlier run of the same question verified one axis for the
> minority while a second came back `conflicting`, and the head-count then crowned the majority —
> publishing "a permanent, total loss" while the pipeline's own sources said otherwise. The label
> validator caught it during export. Evidence is now **sticky**: a position that lost an axis to
> cited sources cannot win the run on a vote. See DESIGN.md §7.

## 2. The gate's payoff — `unanimous`

`docs/demo/01KZX5C4WT0EGQTJ654NWKQ5CZ.json`

All three models recommended starting with a monorepo, for the same reasons. The comparator
returned `none` and justified it explicitly: the only candidate difference was implementation
detail, which does not change what the user does.

The resolver never ran — the trace shows that stage as *skipped — no material dispute*. The caveats
still do work: they name the assumptions the recommendation rests on, state that no dissent
survived, and flag that the advice is stage-bound.

## 3. A debate that honestly failed — `majority`

`docs/demo/01KZX5C7Y3AKP2RSE4Z42ES27F.json`

Two models said profile the suite first; one said parallelise across CI workers first. Typed
`approach` — no external arbiter exists — so it went to debate, and both rounds ran:

| Round | s1 (parallelise) | s2 (profile first) |
|---|---|---|
| 1 | DEFEND | DEFEND |
| 2 | **REVISE** | DEFEND |

Neither conceded, so the dispute closed **unresolved** — *"an honest standoff, not a failure"* —
and the ladder fell to rung 3. The dissent was **informed**: its blind peer prediction had named
the eventual majority position and it disagreed anyway. That is what pulls confidence from high to
medium and puts the surviving position in the caveats as a live alternative.

## 4. Ambiguity branched, then a genuine tie — `tie-break`

`docs/demo/01KZX5E0SDZKBR3GRWAY9TZY1N.json`

The richest tape in the pack: **three stances, one per model, and two disputes of different types.**

- `d1` **interpretation** — *is the $5,000 annual or monthly?* One model read it as monthly. Two
  valid readings cannot defeat each other, so this closed as `branch` with **no debate**, and the
  answer carries the alternative as a conditional line.
- `d2` **approach** — given an annual budget, buy cheap SaaS or self-host? Debated for two rounds
  between the two stances that held a position; one revised, neither conceded, closed unresolved.

That left three stances of one model each — a genuine three-way tie with no majority to count. The
ladder fell to rung 4 and broke the tie on the **first published criterion: quality of engagement
in the debate transcript**, with `tie_break_reason` in the response. Confidence is `low`, which is
the honest reading of an answer chosen because one side argued more carefully than another.

## 5. An attack that landed — `rigorous`

`docs/demo/01KZX56JVSDXR7902KDV0P1FEM.json`

The same monorepo question as #2, in rigorous mode. Two things happen that `fast` skips:

**The gate ran twice**, the second time with the answers in reversed order. Both passes returned
`none`, so `unstable: false` — the position-bias check actually ran and found nothing, rather than
being assumed away. (The trace shows three comparator calls, not two: the first pass failed to
parse and was repaired once, which the tape now marks `repair_attempt`.)

**Then the consensus was attacked.** `x-ai/grok-4.6` — a family absent from the panel — was asked
for the strongest reason the agreement is wrong, and it found one:

> The consensus treats "start monorepo, split later" as cheaply reversible and as the right default
> even when stacks differ. For a typical B2B SaaS (TS/React UI + Python/Go/Rails API + infra), there
> is little real shared code…

It judged its own objection as landing, so confidence dropped from **high to medium** and the attack
became the first caveat on an answer that would otherwise have shipped unqualified. Three extra
calls bought one notch of honesty about the case this system is weakest at: the one where nothing on
the panel disagreed.

Nothing changed about the *recommendation* — a landed attack does not open a debate, because a
non-panelist advocate would get a vote the user never granted.

---

## Coverage, honestly

Observed live across these five runs: rungs **0, 2, 3, 4**; verification `supports`; interpretation
branching; a two-round debate with a REVISE and no concession; informed and oblivious dissent; a
three-way stance split; sticky evidence; both rigorous-mode mechanisms, with the red team landing.

Still not observed live, covered only by the offline suite: rung **1** (`debate-resolved` — needs a
model to concede *and* name the claim it withdraws) and rung **5** (`floor`). Live models concede
rarely enough that catching one is luck rather than a demonstration, and the floor requires every
tie-break criterion to come out level.

What CI pins is each *rung*, on a scripted panel — so a change that makes a rung publish the wrong
label or confidence fails before it reaches a live run. Nothing in CI guarantees this particular
question still lands on rung 2 next month; that depends on what the models say. These five tapes
are a record of what happened, not a promise about what will.
