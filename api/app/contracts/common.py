"""Shared enums. Kept in one place because several of these values cross the API
boundary into the frontend and are asserted on in tests."""

from enum import StrEnum


class Mode(StrEnum):
    """A single flag trading cost for scrutiny."""

    FAST = "fast"
    RIGOROUS = "rigorous"


class Stage(StrEnum):
    GUARD = "guard"
    FANOUT = "fanout"
    COMPARE = "compare"
    RESOLVE = "resolve"
    FINALIZE = "finalize"


class Role(StrEnum):
    """Every model seat. The panel is the caller's choice; every other seat is the
    system's, because control flow must never depend on the reliability of a model
    someone else picked."""

    PANEL = "panel"
    NORMALIZER = "normalizer"
    COMPARATOR = "comparator"
    VERIFIER = "verifier"
    SYNTHESIZER = "synthesizer"
    RED_TEAM = "red_team"
