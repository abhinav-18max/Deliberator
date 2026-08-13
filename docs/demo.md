# Demonstration

Four real deliberations, run against live models through the HTTP API. The full tapes are in
`docs/demo/*.json` — every panel answer, the gate's justification, each debate turn with its
steelman, the citations, and the rung taken.

```bash
cd api && uv run python -m app.demo.seed   # load the tapes into Mongo (no API key needed)
make web                                   # then open http://localhost:3000/runs
```

Seeding validates each tape on the way in: a fixture whose label its own events do not support is
rejected rather than shown, because the product's central claim is that labels are checkable.

Panel for all four: `openai/gpt-5.2`, `deepseek/deepseek-v3.2`, `qwen/qwen3-max` — three distinct
families, all off-panel from every referee seat. Referees: comparator `google/gemini-2.5-pro`,
verifier `anthropic/claude-haiku-4.5` (gateway retrieval), synthesizer `anthropic/claude-sonnet-5`.

| # | Task | Result | Calls | Cost | Wall clock | What it demonstrates |
|---|---|---|---|---|---|---|
| 1 | `git reset --hard HEAD~1` semantics | **verified / high** (rung 2) | 9 | $0.0689 | 65s | Evidence beating a head-count |
| 2 | Monorepo or separate repos, 6 engineers | **unanimous / high** (rung 0) | 5 | $0.0270 | 72s | The gate's payoff — 5 calls, not 9 |
| 3 | 40-minute CI suite, what first | **majority (2/3) / medium** (rung 3) | 9 | $0.0420 | 78s | A debate that honestly failed |
| 4 | $5,000 observability budget | **majority (2/3) / high** (rung 3) | 6 | $0.0500 | 218s | Interpretation branched, not debated |

Run 4's 218 seconds is worth noting rather than hiding: the comparator spent most of it on three
long answers. Latency is the honest cost of the pipeline, which is why the interface streams stage
transitions instead of showing a spinner.

---

## 1. Evidence beats the majority — `verified`

`docs/demo/01KZX23XVNPYN7S1BG6J7G6FX7.json`

Two models said a hard reset loses the commit and all uncommitted work permanently. One said the
commit is reflog-recoverable and untracked files survive. The gate returned **material** and
extracted two `factual` disputes, each with a search query:

- *Is the commit removed by `git reset --hard` permanently lost, or recoverable?*
- *Does `git reset --hard` affect untracked files?*

Both were checked with two search framings each. Both came back `supports` with 10 citations, and
the evidence favoured the **single-model minority**. The answer now states the commit is typically
reflog-recoverable and untracked files are untouched — the opposite of what two of three models
said.

This is the case the whole product exists for: a 2–1 majority was overturned by cited sources, and
the label says `verified` rather than `majority` so the user knows *why* to trust it.

> **A bug this exposed.** The first time this ran, one axis verified for the minority while the
> other came back `conflicting`, and the run then took rung 3 and crowned the majority stance —
> publishing "a permanent, total loss" while the pipeline's own verification said otherwise. The
> label validator caught it during export. Evidence is now **sticky**: a position that lost an axis
> to cited sources cannot win the run on a head-count. See DESIGN.md §7.

## 2. The gate's payoff — `unanimous`

`docs/demo/01KZWY7GRQN32BKBJVJYEHVX2Z.json`

All three models recommended starting with a monorepo. The comparator clustered them into one
stance and returned `none`, justifying it explicitly: *"The strongest candidate for a disagreement
is the level of implementation detail provided"* — which does not change what the user does.

The resolver never ran. **5 calls instead of 9**, and the trace shows the resolve stage as
*skipped — no material dispute*. The caveats still do real work: the answer names the assumptions
it rests on, states plainly that no dissent survived, and flags that the recommendation is
time-bound.

## 3. A debate that honestly failed — `majority`

`docs/demo/01KZWXEV775DA3D5DMJ334PCY8.json`

Two models said profile the test suite first; one said parallelise across CI workers first. Typed
`approach` — no external arbiter exists — so it went to debate. Both rounds ran:

| Round | s1 (profile first) | s2 (parallelise first) |
|---|---|---|
| 1 | DEFEND | DEFEND |
| 2 | **REVISE** | DEFEND |

In round 2 gpt-5.2 revised: *"Given the explicit constraint that the team is currently blocked by a
40-minute feedback loop, the immediacy and typically low implementation overhead of CI
parallelisation outweighs doing deeper profiling as the very first step."* Neither side conceded,
so the dispute closed **unresolved** — *"an honest standoff, not a failure"* — and the ladder fell
to rung 3.

The dissent was classified **informed**: qwen's blind peer prediction had correctly named the
profiling-first answer as the likely consensus, and it disagreed anyway. That is what pulls
confidence from high to **medium**, and the surviving position is written into the caveats as a
live alternative rather than dropped.

## 4. Ambiguity branched, not battled — `majority` with a conditional

`docs/demo/01KZWY9Q07QPWCVX64NQ2CB5JX.json`

Two models read "$5,000 budget" as annual and recommended open-source tooling. One read it as
monthly and recommended a premium managed suite. The comparator caught it from the declared
assumptions and typed it `interpretation`:

> *"The models fundamentally disagree on whether the $5,000 budget is annual or monthly. This leads
> to a 12x difference in recommended spending and completely different purchasing strategies."*

**No debate was run** — two valid readings of an ambiguous task cannot defeat each other, so the
dispute closed as `branch`. The answer commits to the majority reading and carries the alternative
as a conditional: *"If you confirm the $5,000 is monthly rather than annual, the entire
recommendation changes."*

The deliberation found a hidden decision variable in the user's own question, which is more useful
than either answer alone.

---

## Coverage, honestly

Observed live in these four runs: rungs **0**, **2**, **3**; verification `supports` and
`conflicting`; interpretation branching; a two-round debate with a REVISE; informed dissent;
sticky evidence.

Not observed live, and covered only by the offline suite: rung **1** (`debate-resolved` — needs a
model to actually concede and name the claim it withdraws), rung **4** (`tie-break`), rung **5**
(`floor`), and rigorous mode's red team. Those paths are exercised by `tests/test_pipeline.py`
against a scripted provider, where a concession or an even split can be forced; live models
concede rarely enough that catching one is a matter of luck rather than a demonstration.

To be precise about what CI pins: the suite reproduces each *rung* on a scripted panel, not these
specific tasks. So a change that would make a rung publish the wrong label or confidence fails
before it reaches a live run — but nothing in CI guarantees that this particular question still
lands on rung 2 next month, because that depends on what the models say.
