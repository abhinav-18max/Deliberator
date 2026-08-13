# Delibrator

Ask several models the same question independently, compare their answers, debate only the
differences that would change what you do, and return **one** answer labelled with how it won.

- **Design and reasoning:** [DESIGN.md](DESIGN.md)
- **Worked examples with real traces:** [docs/demo.md](docs/demo.md)
- **Figures and borrowed principles:** the app's own `/architecture` page, once `make web` is running

```
task ─► GUARD ─► FAN-OUT ─► COMPARE ─┬─► RESOLVE ─► FINALIZE ─► answer + label + confidence
        fence    parallel,   the gate │  verify /   the ladder
        verbatim isolated             │  branch /
                                      └──► debate
                     NONE / SURFACE ──────────────► (skip straight to finalize)
```

## Requirements

Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+, a MongoDB connection string
(Atlas free tier is fine), and an [OpenRouter](https://openrouter.ai) API key.

## Setup

```bash
make install                  # uv sync + npm install
cp api/.env.example api/.env  # then fill in the two values below
```

`api/.env` needs:

```
OPENROUTER_API_KEY=sk-or-v1-...
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
```

Then check the machine before running anything:

```bash
make doctor
```

`doctor` resolves every referee seat against OpenRouter's **live** catalogue, places one real
tiny call per seat, and pings Mongo. It reports which invariants are satisfied by data rather than
by assumption. Model slugs are retired regularly, so if a pin has rotted it tells you here — with
the closest available replacement — instead of failing three stages into a deliberation someone is
watching. Expect output like:

```
referee seats
  [  ok] comparator -> google/gemini-2.5-pro (comparator_v1)
         · probe ok via google/gemini-2.5-pro
  [  ok] synthesizer -> anthropic/claude-sonnet-5 (synthesizer_v1)
         · probe ok via anthropic/claude-sonnet-5 — strict routing had no endpoint, ran unpinned
0 problem(s), 0 warning(s)
```

## Run it

Two terminals:

```bash
make api    # http://localhost:8000
make web    # http://localhost:3000
```

Open <http://localhost:3000>, pick a panel (three distinct families by default), and ask
something with a real decision in it. The stage timeline updates live; the trace below the answer
is the full record.

Three pages:

| Route | What it is |
|---|---|
| `/` | Composer — task, context, panel, mode |
| `/runs` | Every past deliberation with its label, cost and call count |
| `/architecture` | The three figures, the borrowed principles, the invariants, and how each claim is checked |

## Make targets

| Target | What it does |
|---|---|
| `make doctor` | Resolve + probe every seat, check Atlas, print the config fingerprint |
| `make test` | 53 tests, entirely offline — no API key or database needed |
| `make eval` | Comparator regression. MATERIAL recall must stay at 1.0 |
| `make lint` | ruff |
| `make api` / `make web` | Dev servers |

`make test` and `make eval` need no network: the suite drives the real pipeline through a scripted
provider, and the eval replays recorded completions.

## Reading a trace

The trace is the explanation, so every claim in the answer is attributable. In the UI each row is
one pipeline step; in Mongo it is one document in `events`.

- **panel.answer** — the answer, its key claims, its *declared assumptions*, and its blind
  prediction of what other models would conclude
- **compare.verdict** — `none` / `surface` / `material`, the justification (a `none` verdict has to
  argue for itself), and the stance clusters with membership
- **dispute.opened** — the axis, its type, and the `if A … if B …` sentence that makes it material
- **verify.result** — the outcome, both search framings, and citations, with the ones that *carry
  the verdict* marked
- **debate.turn** — actions with reasons, plus the steelman each side had to state before
  responding
- **ladder.rung** — which rung was taken and the confidence derived from it

To check a stored run's label against its own tape:

```bash
cd api && uv run python -m app.label_validator <run_id>
```

## Layout

```
api/
  app/
    contracts/       typed stage boundaries (pydantic); wire.py is what models emit
    stages/          guard · fanout · normalize · compare · verify · debate · synthesize · redteam
    prompts/         versioned prompt files; the version is part of every call key
    providers/       OpenRouter transport, catalogue, scripted fake, record/replay
    store/           append-only event tape (Mongo) + in-memory implementation
    cluster.py       pure: re-clustering, vote transfer, convergence
    ladder.py        pure: rung → label → confidence
    label_validator.py  pure: does the tape support the published label?
    orchestrator.py  the flow — no prompts, no judgement calls
    evalset/         labelled comparator cases + harness
  config.yaml        panel shortlist, referee chains, caps, verified configs
web/                 composer, live stage timeline, answer card, trace viewer
```

## Configuration

`api/config.yaml` is the operator surface. The panel is the caller's choice; every referee seat is
the operator's, because control flow must never depend on the reliability of a model someone else
picked. Callers may override only the roles in `allow_request_overrides` — never the comparator.

Invariants enforced in `roles.py`, each with a defined failure mode rather than a generic error:

| Invariant | On violation |
|---|---|
| Comparator emits strict schema | Reject the config — its output *is* the control flow |
| Verifier can ground | Disable rung 2 entirely; never guess |
| Synthesizer / verifier off-panel | Substitute down the chain, else stamp the run and demote confidence |
| Referee temperature | Clamped to 0 — control flow must not sample |
| Envelope fits every panel window | Refuse the selection; truncating some models fabricates disagreement |
| Panel ≥ quorum | Below 2, degrade to single-answer mode with a warning |

## Not built

No auth or multi-tenancy. No token-level streaming of panel answers — stage-level is the honest
unit, since a half-written answer is not a position. No prompt playground. No embedding index
(cosine similarity measures wording; two answers can be neighbours in embedding space and
recommend opposite actions). Live event fan-out is in-process, so multiple API workers would need
the change-stream swap noted in `store/broadcast.py`. Full limitations, including the ones that are
properties rather than gaps, are in [DESIGN.md §8](DESIGN.md).
