"""The validator has to reject tapes that do not support their label.

Every pipeline test already asserts zero violations on a real run, which proves the honest
direction. These tests prove the other one: that a tape which lies gets caught. Each case
tampers with exactly one field, so a passing suite means each rule is doing its own work
rather than being carried by another.
"""

from app.contracts import EventType, TraceEvent
from app.label_validator import validate


def tape(*payloads: tuple[EventType, dict]) -> list[TraceEvent]:
    return [
        TraceEvent(run_id="r", seq=i + 1, type=type_, payload=payload)
        for i, (type_, payload) in enumerate(payloads)
    ]


def final(**overrides) -> dict:
    base = {
        "final_answer": "Use a token bucket.",
        "label": "unanimous",
        "resolution": "unanimous",
        "confidence": "high",
        "caveats": [],
        "rung": 0,
        "tie_break_reason": None,
        "unresolved_disputes": [],
        "dissent": None,
        "panel": ["m1", "m2"],
        "referees": [],
        "gate_validated": True,
        "calls": 0,
        "cost_micros": 0,
        "duration_ms": 10,
    }
    base.update(overrides)
    return base


def rules(violations) -> set[str]:
    return {v.rule for v in violations}


def test_a_supported_unanimous_tape_passes():
    events = tape(
        (EventType.COMPARE_VERDICT, {"verdict": "none", "justification": "same", "stances": []}),
        (EventType.LADDER_RUNG, {"rung": 0, "label": "unanimous", "confidence": "high"}),
        (EventType.RUN_FINAL, final()),
    )
    assert validate(events) == []


def test_unanimous_over_a_material_verdict_is_rejected():
    events = tape(
        (
            EventType.COMPARE_VERDICT,
            {"verdict": "material", "justification": "differs", "stances": []},
        ),
        (EventType.RUN_FINAL, final()),
    )
    assert "unanimous-needs-gate" in rules(validate(events))


def test_a_label_that_does_not_match_its_rung_is_rejected():
    events = tape((EventType.RUN_FINAL, final(rung=5, label="unanimous")))
    assert "label-matches-rung" in rules(validate(events))


def test_debate_resolved_without_a_debate_closure_is_rejected():
    events = tape(
        (EventType.RUN_FINAL, final(rung=1, label="debate-resolved", resolution="debate-resolved"))
    )
    assert "debate-needs-a-closure" in rules(validate(events))


def test_verified_without_citations_is_rejected():
    """The central rule: this label may not be reached by a model answering from memory."""
    events = tape(
        (
            EventType.VERIFY_RESULT,
            {"dispute_id": "d1", "outcome": "supports", "citations": [], "supporting_urls": []},
        ),
        (
            EventType.DISPUTE_CLOSED,
            {"dispute_id": "d1", "mechanism": "verification", "resolved": True},
        ),
        (EventType.RUN_FINAL, final(rung=2, label="verified", resolution="verified")),
    )
    assert "verified-needs-an-artifact" in rules(validate(events))


def test_verified_with_a_cited_artifact_passes():
    events = tape(
        (
            EventType.VERIFY_RESULT,
            {
                "dispute_id": "d1",
                "outcome": "supports",
                "citations": [{"url": "https://example.org/a"}],
                "supporting_urls": ["https://example.org/a"],
            },
        ),
        (
            EventType.DISPUTE_CLOSED,
            {"dispute_id": "d1", "mechanism": "verification", "resolved": True},
        ),
        (EventType.LADDER_RUNG, {"rung": 2, "label": "verified", "confidence": "high"}),
        (EventType.RUN_FINAL, final(rung=2, label="verified", resolution="verified")),
    )
    assert validate(events) == []


def test_dropping_to_a_vote_after_argument_settled_it_is_rejected():
    events = tape(
        (
            EventType.DISPUTE_CLOSED,
            {"dispute_id": "d1", "mechanism": "debate", "resolved": True, "winning_stance": "s1"},
        ),
        (EventType.RUN_FINAL, final(rung=3, label="majority", resolution="majority (2/3)")),
    )
    assert "voting-sits-below-argument" in rules(validate(events))


def test_a_tie_break_must_publish_its_reason():
    events = tape(
        (EventType.RUN_FINAL, final(rung=4, label="tie-break", confidence="low")),
    )
    assert "tie-break-is-published" in rules(validate(events))


def test_confidence_that_the_tape_does_not_derive_is_rejected():
    # Majority over informed dissent derives medium; publishing high is the exact overstatement
    # the label contract exists to prevent.
    events = tape(
        (
            EventType.RUN_FINAL,
            final(rung=3, label="majority", confidence="high", dissent="informed"),
        ),
    )
    assert "confidence-is-derived" in rules(validate(events))


def test_an_unvalidated_gate_must_show_its_demotion():
    events = tape((EventType.RUN_FINAL, final(gate_validated=False, confidence="high")))
    assert "confidence-is-derived" in rules(validate(events))
    # And the demoted value passes.
    ok = tape(
        (EventType.COMPARE_VERDICT, {"verdict": "none", "justification": "x", "stances": []}),
        (EventType.LADDER_RUNG, {"rung": 0, "label": "unanimous", "confidence": "medium"}),
        (EventType.RUN_FINAL, final(gate_validated=False, confidence="medium")),
    )
    assert validate(ok) == []


def test_confidence_drifting_from_the_ladder_is_rejected():
    events = tape(
        (EventType.COMPARE_VERDICT, {"verdict": "none", "justification": "x", "stances": []}),
        (EventType.LADDER_RUNG, {"rung": 0, "label": "unanimous", "confidence": "medium"}),
        (EventType.RUN_FINAL, final(confidence="high")),
    )
    assert "confidence-does-not-drift" in rules(validate(events))


def test_a_conceded_claim_reappearing_in_the_answer_is_rejected():
    claim = "a leaky bucket smooths traffic better than a token bucket does"
    events = tape(
        (
            EventType.DEBATE_TURN,
            {
                "dispute_id": "d1",
                "round": 1,
                "stance_id": "s2",
                "model": "m2",
                "steelman": "s",
                "response": "r",
                "actions": [
                    {
                        "against_stance": "s1",
                        "action": "concede",
                        "because": "evidence",
                        "withdrawn_claim": claim,
                    }
                ],
                "parse_degraded": False,
            },
        ),
        (
            EventType.DISPUTE_CLOSED,
            {"dispute_id": "d1", "mechanism": "debate", "resolved": True, "winning_stance": "s1"},
        ),
        (
            EventType.RUN_FINAL,
            final(
                rung=1,
                label="debate-resolved",
                resolution="debate-resolved",
                final_answer=f"Use a token bucket. Note that {claim}.",
            ),
        ),
    )
    assert "conceded-claims-stay-dead" in rules(validate(events))


def test_unresolved_disputes_without_a_caveat_are_rejected():
    events = tape(
        (
            EventType.RUN_FINAL,
            final(rung=3, label="majority", confidence="medium", unresolved_disputes=["d1"]),
        ),
    )
    assert "dissent-is-named" in rules(validate(events))


def test_accounting_must_add_up():
    events = tape(
        (EventType.COMPARE_VERDICT, {"verdict": "none", "justification": "x", "stances": []}),
        (EventType.MODEL_CALL, {"role": "panel", "cost_micros": 100}),
        (EventType.MODEL_CALL, {"role": "panel", "cost_micros": 100}),
        (EventType.RUN_FINAL, final(calls=5, cost_micros=999)),
    )
    assert "accounting-is-complete" in rules(validate(events))


def test_a_tape_with_no_terminal_event_is_rejected():
    events = tape((EventType.STAGE_ENTERED, {"stage": "guard"}))
    assert "terminates" in rules(validate(events))


def test_a_run_that_errored_is_not_a_contract_violation():
    events = tape(
        (EventType.STAGE_ENTERED, {"stage": "fanout"}),
        (EventType.RUN_ERROR, {"detail": "no model produced an answer"}),
    )
    assert validate(events) == []
