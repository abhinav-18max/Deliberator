"""Structural invariants, asserted against the source itself.

Some of this design's guarantees are not observable from behaviour on a passing run — an
append-only tape looks identical to a mutable one until the day something updates it, and the
separation between control flow and judgement erodes one convenient import at a time. These tests
read the code so those properties fail the build rather than decaying quietly.
"""

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

PURE_MODULES = ["cluster.py", "ladder.py", "label_validator.py"]
IO_IMPORTS = {"asyncio", "httpx", "pymongo", "fastapi"}
IO_PACKAGES = {"providers", "store", "calls", "stages", "prompts"}


def _module_level_imports(path: Path) -> set[str]:
    """Imports at module scope only. A lazy import inside a CLI entry point does not make a
    module impure for the purposes this rule protects."""
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            names.add(root or (node.names[0].name if node.names else ""))
    return names


def test_the_event_tape_is_append_only():
    """`events` may be inserted into and read from. Nothing else.

    Mongo will not enforce this, so the discipline has to be checked somewhere. `runs` is a
    projection and is deliberately exempt — it is rebuildable from the tape.
    """
    source = (APP / "store" / "mongo.py").read_text()
    calls = re.findall(r"self\.events\.([a-z_]+)", source)
    assert calls, "expected to find event-collection calls to check"
    allowed = {"insert_one", "find", "find_one", "create_index"}
    assert set(calls) <= allowed, f"non-append operation on the tape: {set(calls) - allowed}"


def test_the_orchestrator_holds_no_prompts():
    """Judgement lives in models, and the wording of that judgement lives in prompt files. An
    orchestrator that renders a prompt has started making judgement calls.

    Checked as imports and calls rather than as the word "prompt", which appears in the module's
    own docstring making exactly this claim.
    """
    tree = ast.parse((APP / "orchestrator.py").read_text())
    imports = _module_level_imports(APP / "orchestrator.py")
    assert "prompts" not in imports, "the orchestrator must not reach for prompt templates"
    rendered = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "render"
    ]
    assert not rendered, "the orchestrator renders a prompt"


def test_the_pure_modules_stay_pure():
    """The design's invariants live in these three. They are property-testable only while they
    take dataclasses and return dataclasses."""
    for name in PURE_MODULES:
        imports = _module_level_imports(APP / name)
        assert not (imports & IO_IMPORTS), f"{name} imports I/O: {imports & IO_IMPORTS}"
        assert not (imports & IO_PACKAGES), f"{name} imports a side-effecting package"


def test_strict_routing_is_never_pinned_on_a_caller_selected_model():
    """`require_parameters` belongs to seats the operator owns. Applying it to panel or debate
    calls would let a caller's model selection decide whether a request is routable at all."""
    source = (APP / "providers" / "openrouter.py").read_text()
    referee_line = re.search(r"REFEREE_ROLES = \{([^}]*)\}", source)
    assert referee_line, "expected a REFEREE_ROLES set"
    roles = {r.strip().strip('\"') for r in referee_line.group(1).split(",") if r.strip()}
    assert "panel" not in roles and "debater" not in roles
    assert roles == {"comparator", "verifier", "synthesizer", "normalizer", "red_team"}


def test_the_comparator_is_not_caller_overridable():
    """The gate's output *is* the control flow, so it is the one seat a request may not swap."""
    request_source = (APP / "contracts" / "request.py").read_text()
    assert "Role.COMPARATOR" in request_source, "the request contract must reject this role"
    config = (Path(__file__).resolve().parents[1] / "config.yaml").read_text()
    overrides = re.search(r"allow_request_overrides:\s*\[([^\]]*)\]", config)
    assert overrides, "expected allow_request_overrides in config.yaml"
    assert "comparator" not in overrides.group(1)


def test_every_prompt_version_in_config_has_a_file():
    """A prompt version is part of every call key. A missing file is a runtime failure at the
    worst moment, so it is checked here instead."""
    config = (Path(__file__).resolve().parents[1] / "config.yaml").read_text()
    for version in re.findall(r"prompt_version:\s*(\S+)", config):
        assert (APP / "prompts" / f"{version}.md").exists(), f"no prompt file for {version}"
