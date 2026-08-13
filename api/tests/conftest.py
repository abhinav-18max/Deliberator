"""Builders for the pure-module and pipeline tests."""

from typing import Any

from app.contracts import (
    Action,
    DebateTurn,
    Dispute,
    DisputeOutcome,
    DisputeType,
    EventType,
    Mechanism,
    PanelAnswer,
    Stance,
    TraceEvent,
    TurnAction,
    Verdict,
)
from app.ladder import LadderInput
from app.settings import Caps, Config


def stance(sid: str, members: list[str], strongest: str | None = None) -> Stance:
    return Stance(
        id=sid,
        summary=f"stance {sid}",
        members=members,
        strongest=strongest or members[0],
    )


def action(
    against: str, kind: Action, because: str = "", withdrawn: str | None = None
) -> TurnAction:
    if kind is not Action.DEFEND and not because:
        because = "the opposing point about latency was decisive"
    return TurnAction(
        against_stance=against, action=kind, because=because, withdrawn_claim=withdrawn
    )


def turn(
    dispute: str,
    sid: str,
    model: str,
    actions: list[TurnAction],
    *,
    rnd: int = 1,
    steelman: str = "their strongest form is that bursts must be absorbed",
    degraded: bool = False,
) -> DebateTurn:
    return DebateTurn(
        dispute_id=dispute,
        round=rnd,
        stance_id=sid,
        model=model,
        steelman=steelman,
        response="response body",
        actions=actions,
        parse_degraded=degraded,
    )


def dispute(did: str = "d1", kind: DisputeType = DisputeType.APPROACH) -> Dispute:
    return Dispute(
        id=did,
        type=kind,
        question="which rate limiter",
        decision_impact="if bursts matter use token bucket; if smoothness matters use leaky bucket",
        positions={"s1": "token bucket", "s2": "leaky bucket"},
        search_query="token bucket vs leaky bucket burst behaviour"
        if kind is DisputeType.FACTUAL
        else None,
    )


def outcome(
    did: str = "d1",
    *,
    mechanism: Mechanism = Mechanism.DEBATE,
    resolved: bool = True,
    winner: str | None = "s1",
    rounds: int = 1,
) -> DisputeOutcome:
    return DisputeOutcome(
        dispute_id=did,
        mechanism=mechanism,
        resolved=resolved,
        winning_stance=winner if resolved else None,
        rounds=rounds,
    )


def answer(model: str, assumptions: int = 0, prediction: str | None = "x") -> PanelAnswer:
    return PanelAnswer(
        model=model,
        answer=f"answer from {model}",
        key_claims=["claim one"],
        assumptions=[f"assumption {i}" for i in range(assumptions)],
        expected_consensus=prediction,
    )


# --- pipeline fixtures -----------------------------------------------------------

PANEL = ["m1", "m2", "m3"]


def make_config(**overrides: Any) -> Config:
    """A config with fake slugs. Referees are off-panel and the comparator is registered as
    verified, so confidence assertions are not silently demoted."""
    base: dict[str, Any] = {
        "caps": Caps().model_dump(),
        "panel_shortlist": PANEL,
        "panel_default": PANEL,
        "roles": {
            "comparator": {
                "chain": ["ref-a"],
                "prompt_version": "comparator_v1",
                "require_structured": True,
            },
            "verifier": {
                "chain": ["ref-web"],
                "prompt_version": "verifier_v1",
                "require_structured": True,
                "require_web": True,
                "off_panel": "require",
            },
            "synthesizer": {
                "chain": ["ref-b"],
                "prompt_version": "synthesizer_v1",
                "require_structured": True,
                "off_panel": "require",
            },
            "normalizer": {
                "chain": ["ref-b"],
                "prompt_version": "normalizer_v1",
                "require_structured": True,
            },
            "red_team": {
                "chain": ["ref-c"],
                "prompt_version": "redteam_v1",
                "require_structured": True,
            },
        },
        "allow_request_overrides": ["synthesizer", "verifier"],
        "verified_configs": [
            {"slug": "ref-a", "prompt_version": "comparator_v1", "material_recall": 1.0}
        ],
    }
    base.update(overrides)
    return Config.model_validate(base)


def panel_out(
    text: str = "use a token bucket",
    claims: list[str] | None = None,
    assumptions: list[str] | None = None,
    prediction: str = "most models will recommend a token bucket",
) -> dict[str, Any]:
    return {
        "answer": text,
        "key_claims": claims if claims is not None else ["token bucket absorbs bursts"],
        "assumptions": assumptions if assumptions is not None else [],
        "expected_consensus": prediction,
    }


def stance_out(sid: str, members: list[str], summary: str = "") -> dict[str, Any]:
    return {
        "id": sid,
        "summary": summary or f"position {sid}",
        "members": members,
        "strongest": members[0],
    }


def dispute_out(
    did: str = "d1",
    kind: str = "approach",
    query: str | None = None,
) -> dict[str, Any]:
    return {
        "id": did,
        "type": kind,
        "question": "which limiter absorbs bursts",
        "decision_impact": "if bursts matter use a token bucket; otherwise use a leaky bucket",
        "positions": [
            {"stance_id": "s1", "position": "token bucket"},
            {"stance_id": "s2", "position": "leaky bucket"},
        ],
        "search_query": query,
    }


def comparison_out(
    verdict: str,
    stances: list[dict[str, Any]],
    disputes: list[dict[str, Any]] | None = None,
    predictions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "justification": "checked the strongest candidate disagreement",
        "stances": stances,
        "disputes": disputes or [],
        "predictions": predictions or [],
    }


def turn_out(
    actions: list[dict[str, Any]], steelman: str = "their strongest form"
) -> dict[str, Any]:
    return {"steelman": steelman, "response": "my response", "actions": actions}


def act(against: str, kind: str, because: str = "", withdrawn: str | None = None) -> dict[str, Any]:
    return {
        "against_stance": against,
        "action": kind,
        "because": because or ("their burst argument was decisive" if kind != "defend" else ""),
        "withdrawn_claim": withdrawn,
    }


def synthesis_out(text: str = "Use a token bucket.", caveats: list[str] | None = None):
    return {"final_answer": text, "caveats": caveats or []}


CITED_URL = "https://example.org/limiters"


def verification_out(
    outcome: str = "supports",
    winner: str | None = "s1",
    cited: bool = True,
    supporting: list[str] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "__parsed__": {
            "outcome": outcome,
            "winning_stance": winner,
            "summary": "the sources agree",
            "supporting_urls": [CITED_URL] if supporting is None else supporting,
        }
    }
    if cited:
        doc["__annotations__"] = [
            {
                "type": "url_citation",
                "url_citation": {
                    "url": "https://example.org/limiters",
                    "title": "Rate limiting",
                    "content": "token buckets absorb bursts",
                    "start_index": 0,
                    "end_index": 20,
                },
            }
        ]
    return doc


async def collect(orchestrator, run_id: str, request) -> list[TraceEvent]:
    return [event async for event in orchestrator.run(run_id, request)]


def payload_of(events: list[TraceEvent], type_: EventType) -> dict[str, Any]:
    return next(e.payload for e in events if e.type is type_)


def all_of(events: list[TraceEvent], type_: EventType) -> list[dict[str, Any]]:
    return [e.payload for e in events if e.type is type_]


def ladder_input(**overrides) -> LadderInput:
    base = {
        "verdict": Verdict.MATERIAL,
        "stances": [stance("s1", ["m1", "m2"]), stance("s2", ["m3"])],
        "disputes": [dispute()],
        "outcomes": [outcome()],
        "verifications": [],
        "predictions": {},
        "answers": [answer("m1"), answer("m2"), answer("m3")],
        "turns": [],
        "floor_model": "m1",
        "dropouts": [],
        "gate_validated": True,
    }
    base.update(overrides)
    return LadderInput(**base)
