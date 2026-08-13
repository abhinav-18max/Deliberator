"""The event tape.

The trace is the explanation: every claim in the final answer has to be attributable
("adopted after the dissent conceded in round 1"). It is simultaneously the audit trail,
the debugging tool, the demo artifact, and — because every model call is recorded with its
call key — the test fixture the eval harness replays.

The tape is the source of truth. The `runs` document is a projection of it and can be
rebuilt by replaying events.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    STAGE_ENTERED = "stage.entered"
    PANEL_ANSWER = "panel.answer"
    PANEL_DROPOUT = "panel.dropout"
    NORMALIZE_APPLIED = "normalize.applied"
    COMPARE_VERDICT = "compare.verdict"
    DISPUTE_OPENED = "dispute.opened"
    VERIFY_RESULT = "verify.result"
    DEBATE_TURN = "debate.turn"
    CLUSTER_CONVERGED = "cluster.converged"
    DISPUTE_CLOSED = "dispute.closed"
    LADDER_RUNG = "ladder.rung"
    MODEL_CALL = "model.call"  # accounting: role, slug, provider, tokens, cost
    RUN_FINAL = "run.final"
    RUN_ERROR = "run.error"


class TraceEvent(BaseModel):
    run_id: str
    seq: int
    type: EventType
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        """Deterministic id makes an append idempotent under retry."""
        return f"{self.run_id}:{self.seq:05d}"

    def to_doc(self) -> dict[str, Any]:
        doc = self.model_dump(mode="json")
        doc["_id"] = self.doc_id
        return doc

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "TraceEvent":
        return cls.model_validate({k: v for k, v in doc.items() if k != "_id"})


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
