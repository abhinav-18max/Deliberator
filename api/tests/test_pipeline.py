"""End-to-end pipeline on the scripted provider.

Each test drives one rung of the ladder through the real orchestrator, real gate, real debate
machine and real synthesizer — only the transport is fake. That is what makes the ladder's
labels testable: a rung is reached because the pipeline reached it, not because a unit test
asserted it in isolation.
"""

from conftest import (
    PANEL,
    act,
    all_of,
    collect,
    comparison_out,
    dispute_out,
    make_config,
    panel_out,
    payload_of,
    stance_out,
    synthesis_out,
    turn_out,
    verification_out,
)

from app.contracts import Confidence, EventType, ResolutionLabel, Rung
from app.contracts.request import DeliberateRequest
from app.orchestrator import Orchestrator
from app.providers.fake import FakeProvider

RUN = "01JTESTRUN0000000000000000"


def request(**overrides) -> DeliberateRequest:
    base = {"task": "pick a rate limiter for a bursty API", "models": PANEL}
    base.update(overrides)
    return DeliberateRequest.model_validate(base)


def orchestrator(responses: dict) -> Orchestrator:
    return Orchestrator(FakeProvider(responses), make_config())


async def test_unanimous_panel_skips_the_resolver_entirely():
    orch = orchestrator(
        {
            "panel:m1": [panel_out()],
            "panel:m2": [panel_out("token bucket, sized for the burst")],
            "panel:m3": [panel_out("a token bucket")],
            "comparator": [
                comparison_out(
                    "none",
                    [stance_out("s1", ["A", "B", "C"])],
                    predictions=[{"model_slug": lbl, "stance_id": "s1"} for lbl in "ABC"],
                )
            ],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)

    assert final["label"] == ResolutionLabel.UNANIMOUS.value
    assert final["confidence"] == Confidence.HIGH.value
    assert final["rung"] == int(Rung.UNANIMOUS)
    # The gate's payoff: no debate, no verification, five calls.
    assert not all_of(events, EventType.DEBATE_TURN)
    assert not all_of(events, EventType.VERIFY_RESULT)
    assert final["calls"] == 5
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


async def test_concession_in_debate_reaches_rung_one():
    orch = orchestrator(
        {
            "panel:m1": [panel_out("token bucket")],
            "panel:m2": [panel_out("token bucket")],
            "panel:m3": [panel_out("leaky bucket")],
            "comparator": [
                comparison_out(
                    "material",
                    [stance_out("s1", ["A", "B"]), stance_out("s2", ["C"])],
                    disputes=[dispute_out()],
                )
            ],
            # Advocates are called in stance order: s1 holds, s2 concedes and names the claim
            # it is giving up.
            "debater": [
                turn_out([act("s2", "defend")]),
                turn_out([act("s1", "concede", withdrawn="token bucket absorbs bursts")]),
            ],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)
    closed = all_of(events, EventType.DISPUTE_CLOSED)

    assert final["label"] == ResolutionLabel.DEBATE_RESOLVED.value
    assert final["confidence"] == Confidence.HIGH.value
    assert len(all_of(events, EventType.DEBATE_TURN)) == 2
    assert closed[0]["mechanism"] == "debate" and closed[0]["resolved"] is True


async def test_grounded_evidence_reaches_rung_two_and_records_citations():
    orch = orchestrator(
        {
            "panel:m1": [panel_out("token bucket")],
            "panel:m2": [panel_out("token bucket")],
            "panel:m3": [panel_out("leaky bucket")],
            "comparator": [
                comparison_out(
                    "material",
                    [stance_out("s1", ["A", "B"]), stance_out("s2", ["C"])],
                    disputes=[dispute_out(kind="factual", query="token bucket burst behaviour")],
                )
            ],
            # One call per framing, both citing sources and agreeing.
            "verifier": [verification_out(), verification_out()],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)
    verify_result = payload_of(events, EventType.VERIFY_RESULT)

    assert final["label"] == ResolutionLabel.VERIFIED.value
    assert verify_result["outcome"] == "supports"
    assert verify_result["citations"][0]["url"] == "https://example.org/limiters"
    assert len(verify_result["queries"]) == 2  # symmetric framing, not one leading query


async def test_uncited_verification_is_never_labelled_verified():
    orch = orchestrator(
        {
            "panel:m1": [panel_out("token bucket")],
            "panel:m2": [panel_out("token bucket")],
            "panel:m3": [panel_out("leaky bucket")],
            "comparator": [
                comparison_out(
                    "material",
                    [stance_out("s1", ["A", "B"]), stance_out("s2", ["C"])],
                    disputes=[dispute_out(kind="factual", query="token bucket burst behaviour")],
                )
            ],
            # Answered from memory: confident, uncited, inadmissible.
            "verifier": [verification_out(cited=False), verification_out(cited=False)],
            # Falls through to debate, where nobody moves.
            "debater": [turn_out([act("s2", "defend")]), turn_out([act("s1", "defend")])],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)

    assert payload_of(events, EventType.VERIFY_RESULT)["outcome"] == "unverifiable"
    assert final["label"] != ResolutionLabel.VERIFIED.value
    assert final["label"] == ResolutionLabel.MAJORITY.value
    assert final["unresolved_disputes"] == ["d1"]


async def test_a_citation_that_was_never_retrieved_invalidates_the_verification():
    """The failure mode gateway retrieval introduces: sources are always attached, so their
    presence alone stops proving the verifier used them. Naming a URL that was not fetched is a
    fabricated citation, and it must discard the result rather than decorate it."""
    orch = orchestrator(
        {
            "panel:m1": [panel_out("token bucket")],
            "panel:m2": [panel_out("token bucket")],
            "panel:m3": [panel_out("leaky bucket")],
            "comparator": [
                comparison_out(
                    "material",
                    [stance_out("s1", ["A", "B"]), stance_out("s2", ["C"])],
                    disputes=[dispute_out(kind="factual", query="token bucket burst behaviour")],
                )
            ],
            "verifier": [
                verification_out(supporting=["https://invented.example/never-fetched"]),
                verification_out(supporting=["https://also-invented.example/nope"]),
            ],
            "debater": [turn_out([act("s2", "defend")]), turn_out([act("s1", "defend")])],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    verification = payload_of(events, EventType.VERIFY_RESULT)
    final = payload_of(events, EventType.RUN_FINAL)

    assert verification["outcome"] == "unverifiable"
    assert "never retrieved" in verification["summary"]
    assert final["label"] != ResolutionLabel.VERIFIED.value


async def test_interpretation_dispute_is_branched_not_debated():
    orch = orchestrator(
        {
            "panel:m1": [panel_out("monthly", assumptions=["budget is monthly"])],
            "panel:m2": [panel_out("monthly", assumptions=["budget is monthly"])],
            "panel:m3": [panel_out("annual", assumptions=["budget is annual"])],
            "comparator": [
                comparison_out(
                    "material",
                    [stance_out("s1", ["A", "B"]), stance_out("s2", ["C"])],
                    disputes=[dispute_out(kind="interpretation")],
                    predictions=[{"model_slug": "C", "stance_id": "s2"}],
                )
            ],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)

    assert not all_of(events, EventType.DEBATE_TURN)  # no fake winner is crowned
    assert payload_of(events, EventType.DISPUTE_CLOSED)["mechanism"] == "branch"
    assert final["label"] == ResolutionLabel.MAJORITY.value
    assert final["unresolved_disputes"] == []


async def test_unparseable_debate_turn_defends_rather_than_conceding():
    orch = orchestrator(
        {
            "panel:m1": [panel_out("token bucket")],
            "panel:m2": [panel_out("token bucket")],
            "panel:m3": [panel_out("leaky bucket")],
            "comparator": [
                comparison_out(
                    "material",
                    [stance_out("s1", ["A", "B"]), stance_out("s2", ["C"])],
                    disputes=[dispute_out()],
                )
            ],
            # Prose instead of the action enum, twice (the repair attempt also fails).
            "debater": [
                "I think we should keep the token bucket, honestly.",
                "Still prose.",
                turn_out([act("s1", "defend")]),
                turn_out([act("s2", "defend")]),
                turn_out([act("s1", "defend")]),
                turn_out([act("s2", "defend")]),
            ],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    turns = all_of(events, EventType.DEBATE_TURN)
    final = payload_of(events, EventType.RUN_FINAL)

    degraded = [t for t in turns if t["parse_degraded"]]
    assert degraded, "an unparseable turn must be recorded, not dropped"
    assert all(a["action"] == "defend" for a in degraded[0]["actions"])
    assert final["label"] != ResolutionLabel.DEBATE_RESOLVED.value
    assert any("recorded as DEFEND" in c for c in final["caveats"])


async def test_gate_failure_falls_to_the_floor_and_says_so():
    orch = orchestrator(
        {
            "panel:m1": [panel_out()],
            "panel:m2": [panel_out()],
            "panel:m3": [panel_out()],
            "comparator": ["not json", "still not json"],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)

    assert final["label"] == ResolutionLabel.FLOOR.value
    assert final["confidence"] == Confidence.LOW.value
    assert any("comparison stage failed" in c for c in final["caveats"])


async def test_refusal_is_a_dropout_not_a_stance():
    orch = orchestrator(
        {
            "panel:m1": [panel_out()],
            "panel:m2": [panel_out()],
            "panel:m3": ["I can't help with that."],
            "comparator": [
                comparison_out(
                    "none",
                    [stance_out("s1", ["A", "B"])],
                    predictions=[{"model_slug": "A", "stance_id": "s1"}],
                )
            ],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    dropouts = all_of(events, EventType.PANEL_DROPOUT)
    final = payload_of(events, EventType.RUN_FINAL)

    assert [d["reason"] for d in dropouts] == ["refusal"]
    assert len(all_of(events, EventType.PANEL_ANSWER)) == 2
    assert any("did not participate (refusal)" in c for c in final["caveats"])


async def test_below_quorum_degrades_to_single_answer_mode():
    orch = orchestrator(
        {
            "panel:m1": [panel_out()],
            "panel:m2": ["I'm sorry, I can't do that."],
            "panel:m3": ["I cannot help with this request."],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    final = payload_of(events, EventType.RUN_FINAL)

    assert final["label"] == ResolutionLabel.FLOOR.value
    assert not all_of(events, EventType.COMPARE_VERDICT)  # nothing to compare
    assert any("below quorum" in c for c in final["caveats"])


async def test_every_call_is_accounted_for_in_the_trace():
    orch = orchestrator(
        {
            "panel:m1": [panel_out()],
            "panel:m2": [panel_out()],
            "panel:m3": [panel_out()],
            "comparator": [
                comparison_out(
                    "none",
                    [stance_out("s1", ["A", "B", "C"])],
                    predictions=[{"model_slug": "A", "stance_id": "s1"}],
                )
            ],
            "synthesizer": [synthesis_out()],
        }
    )

    events = await collect(orch, RUN, request())
    accounting = all_of(events, EventType.MODEL_CALL)
    final = payload_of(events, EventType.RUN_FINAL)

    assert len(accounting) == final["calls"]
    assert {a["role"] for a in accounting} == {"panel", "comparator", "synthesizer"}
    assert all(a["call_key"] for a in accounting)
    assert final["cost_micros"] == sum(a["cost_micros"] for a in accounting)
