"""Every word this system says to a model comes from this directory, at runtime.

Two kinds of file:

*   `<seat>_v<N>.md` — a complete prompt for one seat. The version is part of every call key, so
    editing a prompt correctly invalidates its recorded completions and drops the run out of the
    verified-config registry rather than silently changing behaviour under an unchanged label.
*   `fragments/<name>.md` — a block shared by several prompts, or an instruction the orchestrator
    injects mid-flight (the data-not-instructions rule, a repair re-ask, a section header inside a
    synthesis brief). These live here for the same reason: an instruction hidden in Python can be
    edited without touching a prompt version, which would make `comparator_v1` mean two different
    things on two different days.

Fragments are stored without a trailing newline and returned verbatim, so moving a string out of
code and into a file leaves the rendered prompt byte-identical.

`$name` substitution is used rather than `str.format` so JSON braces inside a prompt need no
escaping. See README.md for the one deliberate exception to "all model-facing wording lives here".
"""

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parent
FRAGMENT_DIR = PROMPT_DIR / "fragments"

# Named so a missing file fails at import of the registry rather than mid-deliberation, and so
# `grep` finds every fragment use from one place.
FRAGMENTS = (
    "data_rule",
    "json_repair",
    "concession_reask",
    "capability_probe",
    "assumption_divergence",
    "brief_winning_header",
    "brief_dissent_header",
    "brief_evidence_header",
    "brief_branch_header",
    "brief_transcript_header",
    "brief_coherence_check",
    "debate_own_header",
)


@lru_cache(maxsize=64)
def _template(version: str) -> Template:
    path = PROMPT_DIR / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt file for version {version!r}")
    return Template(path.read_text())


def render(version: str, **values: str) -> str:
    # substitute (not safe_substitute) so a missing variable fails loudly instead of shipping a
    # prompt with a literal $placeholder in it.
    return _template(version).substitute(**values)


@lru_cache(maxsize=64)
def fragment(name: str) -> str:
    """A shared prompt block, verbatim. Trailing whitespace is stripped so a file that picks up a
    newline from an editor does not change a call key."""
    if name not in FRAGMENTS:
        raise KeyError(f"{name!r} is not a registered fragment; add it to FRAGMENTS")
    path = FRAGMENT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no fragment file at {path}")
    return path.read_text().rstrip("\n")


def versions() -> list[str]:
    """Every complete prompt on disk, for doctor and the architecture tests."""
    return sorted(p.stem for p in PROMPT_DIR.glob("*.md"))
