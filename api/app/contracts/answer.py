"""Panel output.

`expected_consensus` is collected here, blind, and nowhere else: asked after a model
has seen its peers it would be worthless hindsight. It is never allowed to change who
wins — it only distinguishes *informed* dissent (predicted the majority and disagreed
anyway) from *oblivious* dissent (thought everyone agreed with it), which shapes the
caveat and the confidence level.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class PanelAnswer(BaseModel):
    model: str
    answer: str
    key_claims: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    expected_consensus: str | None = None

    # True when the structured fields were recovered by the normalizer instead of
    # produced by the model. A formatting failure must not silently become a
    # confidence input, so unclassifiable dissent is tracked, not guessed.
    normalized: bool = False
    latency_ms: int = 0
    cost_micros: int = 0

    @property
    def has_prediction(self) -> bool:
        return bool(self.expected_consensus and self.expected_consensus.strip())


class DropoutReason(StrEnum):
    TIMEOUT = "timeout"
    ERROR = "error"
    REFUSAL = "refusal"  # a refusal is a dropout, never a dissenting stance
    MALFORMED = "malformed"


class Dropout(BaseModel):
    model: str
    reason: DropoutReason
    detail: str = ""
