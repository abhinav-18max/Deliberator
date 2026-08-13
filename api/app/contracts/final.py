"""The output contract.

The resolution label is the product's honesty guarantee: "everyone agreed instantly" and
"won a vote after a fight" are different products of the same pipeline, and the user
acting on the answer deserves to know which one they received. It is the only thing that
stops a floor-rung answer from impersonating a unanimous one.

Confidence is derived mechanically from the rung (see ladder.py) and never from a model's
self-report, which is documented as miscalibrated and flattery-shaped.
"""

from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class Rung(IntEnum):
    """Tried in order; the answer stops at the first that applies."""

    UNANIMOUS = 0  # the gate found no material dispute — the bypass
    DEBATE = 1
    VERIFIED = 2
    MAJORITY = 3
    TIE_BREAK = 4
    FLOOR = 5


class ResolutionLabel(StrEnum):
    UNANIMOUS = "unanimous"
    DEBATE_RESOLVED = "debate-resolved"
    VERIFIED = "verified"
    MAJORITY = "majority"
    TIE_BREAK = "tie-break"
    FLOOR = "floor"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DissentKind(StrEnum):
    """Weighting for surviving dissent. Informed dissent predicted the majority view and
    rejected it anyway; oblivious dissent never engaged the mainstream at all."""

    INFORMED = "informed"
    OBLIVIOUS = "oblivious"
    UNCLASSIFIABLE = "unclassifiable"  # the model's peer prediction was missing


class RoleAssignment(BaseModel):
    role: str
    slug: str
    prompt_version: str = ""
    off_panel: bool = True


class FinalAnswer(BaseModel):
    final_answer: str
    label: ResolutionLabel
    resolution: str  # rendered for humans, e.g. "majority (2/3)"
    confidence: Confidence
    caveats: list[str] = Field(default_factory=list)

    rung: Rung
    tie_break_reason: str | None = None
    unresolved_disputes: list[str] = Field(default_factory=list)
    dissent: DissentKind | None = None

    # Attribution is incomplete without the cast: how the answer won now includes who
    # refereed, and a run whose gate is unmeasured must not look like one whose isn't.
    panel: list[str] = Field(default_factory=list)
    referees: list[RoleAssignment] = Field(default_factory=list)
    gate_validated: bool = True

    calls: int = 0
    cost_micros: int = 0
    duration_ms: int = 0
