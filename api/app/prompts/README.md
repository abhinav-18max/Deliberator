# Prompts

**Every word this system says to a model is in this directory, and is read at runtime.**

Nothing here is imported as a Python string literal. `loader.render()` and `loader.fragment()`
open the file on use, so a prompt can be edited and the next run picks it up without a code change.

## Naming

| Pattern | What it is |
|---|---|
| `<seat>_v<N>.md` | A complete prompt for one seat. Nine exist: `panel`, `comparator`, `verifier`, `debate_r1`, `debate_r2`, `synthesizer`, `normalizer`, `redteam`. |
| `fragments/<name>.md` | A block shared between prompts, or an instruction the orchestrator injects mid-flight. Registered in `loader.FRAGMENTS`. |

Every version is named in `config.yaml` — the referee seats under `roles.*.prompt_version`, the
re-entrant panel seats under `panel_prompts`. `make doctor` and `tests/test_architecture.py` both
check that each configured version has a file, so a rename fails at boot rather than three stages
into a deliberation.

## Why the version number matters

`prompt_version` is part of every **call key** — the hash over `(role, prompt_version, slug,
messages, schema)` that identifies a model call. Three things follow:

1. Editing a prompt invalidates its recorded completions, so `make eval` and `make demo` re-run
   instead of replaying stale behaviour under a new prompt.
2. The comparator's measured recall belongs to a *(model × prompt version)* pair. Change either and
   the run is stamped `gate: unvalidated` until `make eval` re-measures it.
3. An instruction hidden in Python would break both guarantees: `comparator_v1` could mean two
   different things on two different days, with nothing to notice. That is the reason fragments
   exist rather than being convenient constants.

**Bump the version** (`comparator_v1` → `comparator_v2`) when you change what a prompt asks for.
Edit in place only while iterating before a measurement exists.

## Fragments

| File | Injected where |
|---|---|
| `data_rule.md` | Every prompt that receives user or model content — the data-not-instructions rule |
| `assumption_divergence.md` | The comparator, when the mechanical assumption diff finds something |
| `json_repair.md` | The one repair re-ask after a malformed structured response |
| `concession_reask.md` | A debate turn whose concession named no claim of its own |
| `brief_*_header.md` | Section headers inside the synthesis brief, several of which carry instructions |
| `brief_coherence_check.md` | Added to the brief when axes resolved in favour of different positions |
| `debate_own_header.md` | The fence label for an advocate's own position |
| `capability_probe.md` | `make doctor`'s one real call per referee seat |

Fragments are stored **without a trailing newline** and returned verbatim, so moving a string out
of code into a file leaves the rendered prompt byte-identical — the check being that
`make eval` still reports `recorded 18, live 0`.

## The one deliberate exception

Field descriptions in `app/contracts/wire.py` are model-facing: they are emitted in the strict JSON
schema sent with each referee call. They stay in Python because a field's description belongs
beside the field it describes and the type that parses it — separating them into markdown would let
a schema and its documentation drift apart, which is the failure this directory exists to prevent,
pointed the other way.

## Substitution

`$name` placeholders, via `string.Template`, so JSON braces inside a prompt need no escaping.
`render()` uses `substitute` rather than `safe_substitute`: a missing variable raises instead of
shipping a prompt with a literal `$placeholder` in it.
