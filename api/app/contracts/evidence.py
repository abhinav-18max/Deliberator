"""Verification output.

The admissibility rule is the whole reason to prefer grounded search over "ask a strong
model to check": not that it is more accurate, but that its output is falsifiable in
code. Grounding is model-discretionary — a model may answer from parametric memory and
return no citations at all. That response is an opinion in a lab coat, and it must never
be labelled `verified`.

Three outcomes, not two. `CONFLICTING` is a real result and the highest-value caveat the
product can emit: the panel disagrees on a fact the public record does not settle.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Citation(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    start_index: int | None = None
    end_index: int | None = None


class VerifyOutcome(StrEnum):
    SUPPORTS = "supports"  # one side is backed by cited sources
    CONFLICTING = "conflicting"  # sources disagree or run out
    UNVERIFIABLE = "unverifiable"  # no admissible citation came back at all


class Verification(BaseModel):
    dispute_id: str
    outcome: VerifyOutcome
    winning_stance: str | None = None
    summary: str = ""
    queries: list[str] = Field(default_factory=list)  # both framings, for the trace
    citations: list[Citation] = Field(default_factory=list)

    # The subset of retrieved sources the verifier said its verdict rests on. Required for
    # SUPPORTS, and checked against what was actually retrieved: when retrieval is performed by
    # the gateway rather than the model, "citations are present" no longer proves the model used
    # them, so the model has to name which ones carry the verdict and code confirms they exist.
    supporting_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _admissible(self) -> "Verification":
        if self.outcome is VerifyOutcome.SUPPORTS:
            if not self.citations:
                raise ValueError(
                    f"{self.dispute_id}: SUPPORTS without citations — inadmissible, "
                    "must be recorded as UNVERIFIABLE"
                )
            if not self.supporting_urls:
                raise ValueError(
                    f"{self.dispute_id}: SUPPORTS without naming which sources carry the "
                    "verdict — inadmissible"
                )
            if not self.winning_stance:
                raise ValueError(f"{self.dispute_id}: SUPPORTS without a winning stance")
        return self

    @property
    def resolves(self) -> bool:
        return self.outcome is VerifyOutcome.SUPPORTS and bool(self.citations)
