"""What models are asked to emit, as opposed to what the pipeline stores.

These are kept separate from the internal contracts on purpose. A model should never be
handed fields it has no business setting — cost, latency, which slug produced the answer —
and the strict JSON schema sent to the provider is generated from these shapes, so the
schema and the parser can never drift apart.
"""

from pydantic import BaseModel, Field

from .compare import DisputeType, Verdict
from .debate import Action
from .evidence import VerifyOutcome


class PanelAnswerOut(BaseModel):
    answer: str
    key_claims: list[str] = Field(description="Short, checkable claims your answer rests on.")
    assumptions: list[str] = Field(
        description="Anything you filled in that the task did not state."
    )
    expected_consensus: str = Field(
        description="What will most other capable models conclude on this task?"
    )


class StanceOut(BaseModel):
    id: str
    summary: str
    members: list[str]
    strongest: str


class PositionOut(BaseModel):
    """A pair rather than a map: strict JSON-schema mode cannot express open-ended
    objects, and losing strict mode on the gate is not an acceptable trade."""

    stance_id: str
    position: str


class DisputeOut(BaseModel):
    id: str
    type: DisputeType
    question: str
    decision_impact: str = Field(
        description="If A holds the user should do X; if B holds, Y. If you cannot write "
        "this sentence, the difference is not material."
    )
    positions: list[PositionOut]
    search_query: str | None = Field(
        default=None,
        description="A neutral web query that would settle this. Required for factual "
        "disputes; null when nothing checkable exists.",
    )


class PredictionOut(BaseModel):
    model_slug: str
    stance_id: str | None


class ComparisonOut(BaseModel):
    verdict: Verdict
    justification: str = Field(
        description="Why this verdict. A verdict of none must argue that the strongest "
        "candidate disagreement would not change what the user does."
    )
    stances: list[StanceOut]
    disputes: list[DisputeOut] = Field(default_factory=list)
    predictions: list[PredictionOut] = Field(
        default_factory=list,
        description="For each model, which stance id its expected_consensus pointed at, "
        "or null if it gave no usable prediction.",
    )


class TurnActionOut(BaseModel):
    against_stance: str
    action: Action
    because: str = Field(
        description="What specifically changed your mind. Required unless defending."
    )
    withdrawn_claim: str | None = Field(
        default=None,
        description="The claim of your own you are withdrawing. Required to concede.",
    )


class DebateTurnOut(BaseModel):
    steelman: str = Field(
        description="State the opposing position in its strongest form, before responding."
    )
    response: str
    actions: list[TurnActionOut]


class VerificationOut(BaseModel):
    outcome: VerifyOutcome
    winning_stance: str | None = None
    summary: str = Field(description="What the sources say. Cite them inline.")


class SynthesisOut(BaseModel):
    final_answer: str
    caveats: list[str] = Field(default_factory=list)


class RedTeamOut(BaseModel):
    attack: str = Field(description="The strongest reason this consensus is wrong.")
    lands: bool = Field(description="True only if the attack would change what the user does.")
    question: str | None = None
    decision_impact: str | None = None


class NormalizerOut(BaseModel):
    """Extractive only: every field must quote the answer, never paraphrase it."""

    key_claims: list[str]
    assumptions: list[str]
    expected_consensus: str | None = None
