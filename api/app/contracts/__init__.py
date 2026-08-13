"""Typed contracts for every stage boundary.

Anything that crosses a stage boundary is a pydantic model, so a prompt change that
breaks a shape fails a contract test rather than corrupting a deliberation.
"""

from .answer import Dropout, DropoutReason, PanelAnswer
from .common import Mode, Role, Stage
from .compare import Comparison, Dispute, DisputeType, Stance, Verdict
from .debate import Action, DebateTurn, DisputeOutcome, Mechanism, TurnAction
from .envelope import DATA_RULE, Envelope, fence
from .evidence import Citation, Verification, VerifyOutcome
from .final import (
    Confidence,
    DissentKind,
    FinalAnswer,
    ResolutionLabel,
    RoleAssignment,
    Rung,
)
from .request import DeliberateRequest, RoleOverride
from .trace import EventType, RunStatus, TraceEvent

__all__ = [
    "DATA_RULE",
    "Action",
    "Citation",
    "Comparison",
    "Confidence",
    "DeliberateRequest",
    "DebateTurn",
    "DissentKind",
    "Dispute",
    "DisputeOutcome",
    "DisputeType",
    "Dropout",
    "DropoutReason",
    "Envelope",
    "EventType",
    "FinalAnswer",
    "Mechanism",
    "Mode",
    "PanelAnswer",
    "ResolutionLabel",
    "Role",
    "RoleAssignment",
    "RoleOverride",
    "RunStatus",
    "Rung",
    "Stage",
    "Stance",
    "TraceEvent",
    "TurnAction",
    "Verdict",
    "Verification",
    "VerifyOutcome",
    "fence",
]
