"""Prompts live in versioned files, and the version is part of every call key.

That coupling is deliberate: the comparator's calibration is a property of
`(model, prompt_version)`, not of the pipeline, so a prompt edit must invalidate recorded
completions and drop the run out of the verified-config registry. `$name` substitution is
used rather than `str.format` so JSON braces inside a prompt need no escaping.
"""

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=64)
def _template(version: str) -> Template:
    path = PROMPT_DIR / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt file for version {version!r}")
    return Template(path.read_text())


def render(version: str, **values: str) -> str:
    # substitute (not safe_substitute) so a missing variable fails loudly instead of
    # shipping a prompt with a literal $placeholder in it.
    return _template(version).substitute(**values)
