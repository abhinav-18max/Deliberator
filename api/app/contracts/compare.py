"""The gate's output.

Two rules from the design are enforced here as validators rather than trusted to a
prompt, because both are *constructive tests* and a test can be checked in code:

1.  A dispute is MATERIAL only if you can write the sentence "if A holds do X, if B
    holds do Y". `decision_impact` is that sentence. An axis that cannot produce one is
    SURFACE by construction, not by opinion.
2.  A dispute is `factual` only if a neutral search query can be written for it.
    "Factual" is not the same as "checkable" — a private or predictive claim has no
    external arbiter and must be routed to debate or branched instead.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Verdict(StrEnum):
    NONE = "none"
    SURFACE = "surface"
    MATERIAL = "material"


class DisputeType(StrEnum):
    FACTUAL = "factual"
    INTERPRETATION = "interpretation"
    APPROACH = "approach"


class Stance(BaseModel):
    """A set of answers reaching the same effective conclusion regardless of wording.

    Clustering by position is one pass at any panel size; pairwise matchups would cost
    N(N-1)/2 judgements and are not transitive.
    """

    id: str
    summary: str
    members: list[str] = Field(min_length=1)  # model slugs
    strongest: str  # the member whose argument speaks for the stance in debate

    @model_validator(mode="after")
    def _strongest_is_member(self) -> "Stance":
        if self.strongest not in self.members:
            raise ValueError(f"stance {self.id}: strongest {self.strongest!r} not a member")
        return self


class Dispute(BaseModel):
    id: str
    type: DisputeType
    question: str  # the axis being disagreed on
    decision_impact: str  # "if A holds do X; if B holds do Y" — the materiality test
    positions: dict[str, str]  # stance_id -> that stance's position on this axis
    search_query: str | None = None  # required iff type is factual

    @model_validator(mode="after")
    def _checks(self) -> "Dispute":
        if not self.decision_impact.strip():
            raise ValueError(
                f"dispute {self.id}: no decision impact — SURFACE by construction, not MATERIAL"
            )
        if len(self.positions) < 2:
            raise ValueError(f"dispute {self.id}: needs at least two positions")
        if self.type is DisputeType.FACTUAL and not (self.search_query or "").strip():
            raise ValueError(
                f"dispute {self.id}: typed factual but no search query — not checkable, "
                "reclassify as approach or interpretation"
            )
        return self


class Comparison(BaseModel):
    verdict: Verdict
    justification: str  # a NONE verdict has to argue for itself
    stances: list[Stance]
    disputes: list[Dispute] = Field(default_factory=list)

    # Which stance each model's blind peer-prediction pointed at, keyed by slug. This is
    # what makes the informed/oblivious dissent split mechanical rather than a second
    # judgement call downstream: a dissenter that predicted the eventual majority knew the
    # standard answer and rejected it anyway. None means the model gave no usable
    # prediction, which is recorded as unclassifiable — a formatting failure must not be
    # laundered into a confidence input.
    predictions: dict[str, str | None] = Field(default_factory=dict)

    # Set when the rigorous-mode reversed-order re-run disagreed with the first pass.
    # Instability about whether there is a disagreement is itself treated as one.
    unstable: bool = False

    @model_validator(mode="after")
    def _verdict_matches_disputes(self) -> "Comparison":
        if not self.justification.strip():
            raise ValueError("verdict requires a justification")
        if self.verdict is Verdict.MATERIAL and not self.disputes:
            raise ValueError("MATERIAL verdict with no disputes extracted")
        if self.verdict is not Verdict.MATERIAL and self.disputes:
            raise ValueError(f"{self.verdict} verdict must not carry disputes")
        return self

    def votes(self) -> dict[str, int]:
        """Models per stance. Counted only after argument has had its chance."""
        return {s.id: len(s.members) for s in self.stances}
