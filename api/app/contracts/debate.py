"""Debate output.

Two rules live in this file because both are code-checkable and neither can be left to
a judge:

*   A concession must name a claim the conceder itself made in round 0 and is now
    withdrawing. `withdrawn_claim` carries it, and the orchestrator verifies the claim
    was actually in that model's original record. Polite empty capitulation is trained-in
    behaviour and must not be able to close a real dispute.
*   A turn whose action cannot be parsed defaults to DEFEND. Conservative direction
    matters: a parse failure must never be able to fabricate a concession, because a
    fabricated concession silently closes a dispute and lands the answer on rung 1.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Action(StrEnum):
    DEFEND = "defend"
    REVISE = "revise"
    CONCEDE = "concede"


class Mechanism(StrEnum):
    DEBATE = "debate"
    VERIFICATION = "verification"
    BRANCH = "branch"  # interpretation disputes: no resolution attempted, by design
    UNRESOLVED = "unresolved"  # an honest standoff beats a manufactured consensus


class TurnAction(BaseModel):
    against_stance: str
    action: Action
    because: str = ""  # what specifically changed the model's mind
    withdrawn_claim: str | None = None

    @model_validator(mode="after")
    def _concession_must_cost_something(self) -> "TurnAction":
        if self.action in (Action.CONCEDE, Action.REVISE) and not self.because.strip():
            raise ValueError(f"{self.action} without saying what changed the model's mind")
        return self


class DebateTurn(BaseModel):
    dispute_id: str
    round: int
    stance_id: str
    model: str
    steelman: str  # the opposition's strongest form, stated before responding
    response: str
    actions: list[TurnAction] = Field(default_factory=list)

    # True when the action enum had to be defaulted to DEFEND after a parse failure.
    parse_degraded: bool = False
    cost_micros: int = 0

    @property
    def conceded_to(self) -> list[str]:
        return [a.against_stance for a in self.actions if a.action is Action.CONCEDE]


class DisputeOutcome(BaseModel):
    dispute_id: str
    mechanism: Mechanism
    resolved: bool
    winning_stance: str | None = None
    rounds: int = 0
    note: str = ""

    @model_validator(mode="after")
    def _resolved_has_a_winner(self) -> "DisputeOutcome":
        if self.resolved and self.mechanism is not Mechanism.BRANCH and not self.winning_stance:
            raise ValueError(f"{self.dispute_id}: resolved without a winning stance")
        return self
