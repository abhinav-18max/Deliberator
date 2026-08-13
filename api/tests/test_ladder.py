"""Every path ends in exactly one answer, labelled by how it won."""

from conftest import action, answer, ladder_input, outcome, stance, turn

from app.contracts import (
    Action,
    Citation,
    Confidence,
    DissentKind,
    DropoutReason,
    Mechanism,
    ResolutionLabel,
    Rung,
    Verdict,
    Verification,
    VerifyOutcome,
)
from app.contracts.answer import Dropout
from app.ladder import choose


def test_no_material_dispute_is_unanimous_and_high():
    result = choose(ladder_input(verdict=Verdict.NONE, outcomes=[]))

    assert result.rung is Rung.UNANIMOUS
    assert result.label is ResolutionLabel.UNANIMOUS
    assert result.confidence is Confidence.HIGH


def test_debate_resolution_takes_rung_one():
    result = choose(ladder_input(outcomes=[outcome(mechanism=Mechanism.DEBATE)]))

    assert result.rung is Rung.DEBATE
    assert result.resolution == "debate-resolved"
    assert result.confidence is Confidence.HIGH


def test_verification_resolution_takes_rung_two():
    result = choose(ladder_input(outcomes=[outcome(mechanism=Mechanism.VERIFICATION)]))

    assert result.rung is Rung.VERIFIED
    assert result.confidence is Confidence.HIGH


def test_majority_is_only_reached_when_a_dispute_survived_argument():
    result = choose(
        ladder_input(
            outcomes=[outcome(resolved=False, winner=None, rounds=2)],
            predictions={"m3": "s2"},  # the dissenter expected to be agreed with
        )
    )

    assert result.rung is Rung.MAJORITY
    assert result.resolution == "majority (2/3)"
    assert result.winning_stance == "s1"
    assert result.dissent is DissentKind.OBLIVIOUS
    assert result.confidence is Confidence.HIGH
    assert result.unresolved == ["d1"]
    assert any("Unresolved after 2 round" in c for c in result.caveats)


def test_informed_dissent_lowers_a_majority_to_medium():
    result = choose(
        ladder_input(
            outcomes=[outcome(resolved=False, winner=None)],
            predictions={"m3": "s1"},  # predicted the majority and disagreed anyway
        )
    )

    assert result.dissent is DissentKind.INFORMED
    assert result.confidence is Confidence.MEDIUM


def test_missing_peer_prediction_is_unclassifiable_not_oblivious():
    result = choose(ladder_input(outcomes=[outcome(resolved=False, winner=None)], predictions={}))

    assert result.dissent is DissentKind.UNCLASSIFIABLE
    assert result.confidence is Confidence.MEDIUM


def test_even_split_falls_to_a_published_tie_break():
    turns = [
        turn("d1", "s1", "m1", [action("s2", Action.DEFEND)]),
        turn("d1", "s2", "m2", [action("s1", Action.DEFEND)], degraded=True),
    ]
    result = choose(
        ladder_input(
            stances=[stance("s1", ["m1"]), stance("s2", ["m2"])],
            outcomes=[outcome(resolved=False, winner=None)],
            answers=[answer("m1"), answer("m2")],
            turns=turns,
        )
    )

    assert result.rung is Rung.TIE_BREAK
    assert result.winning_stance == "s1"  # the side whose turn parsed and steelmanned
    assert result.tie_break_reason == "quality of engagement in the debate transcript"
    assert result.confidence is Confidence.LOW


def test_tie_break_falls_through_to_fewer_assumptions():
    result = choose(
        ladder_input(
            stances=[stance("s1", ["m1"]), stance("s2", ["m2"])],
            outcomes=[outcome(resolved=False, winner=None)],
            answers=[answer("m1", assumptions=3), answer("m2", assumptions=1)],
            turns=[],
        )
    )

    assert result.rung is Rung.TIE_BREAK
    assert result.winning_stance == "s2"
    assert result.tie_break_reason == "fewer unstated assumptions"


def test_indistinguishable_split_lands_on_the_floor():
    result = choose(
        ladder_input(
            stances=[stance("s1", ["m1"]), stance("s2", ["m2"])],
            outcomes=[outcome(resolved=False, winner=None)],
            answers=[answer("m1"), answer("m2")],
            turns=[],
            floor_model="m2",
        )
    )

    assert result.rung is Rung.FLOOR
    assert result.winning_model == "m2"
    assert result.winning_stance == "s2"
    assert result.resolution == "floor (m2)"
    assert result.confidence is Confidence.LOW


def test_conflicting_sources_force_low_confidence():
    result = choose(
        ladder_input(
            outcomes=[outcome(resolved=False, winner=None)],
            predictions={"m3": "s2"},  # would otherwise be high
            verifications=[
                Verification(
                    dispute_id="d1",
                    outcome=VerifyOutcome.CONFLICTING,
                    summary="sources split",
                    citations=[Citation(url="https://example.org/a")],
                )
            ],
        )
    )

    assert result.confidence is Confidence.LOW
    assert any("public record did not settle it" in c for c in result.caveats)


def test_unvalidated_gate_demotes_confidence_and_says_so():
    result = choose(ladder_input(gate_validated=False))

    assert result.rung is Rung.DEBATE
    assert result.confidence is Confidence.MEDIUM
    assert any("not in the verified registry" in c for c in result.caveats)


def test_branch_only_disagreement_still_returns_one_answer():
    result = choose(
        ladder_input(
            outcomes=[outcome(mechanism=Mechanism.BRANCH, resolved=False, winner=None)],
            predictions={"m3": "s2"},
        )
    )

    assert result.rung is Rung.MAJORITY  # a primary reading still has to be chosen
    assert result.branches == ["d1"]
    assert result.unresolved == []


def test_dropouts_become_caveats():
    result = choose(
        ladder_input(dropouts=[Dropout(model="m4", reason=DropoutReason.TIMEOUT)])
    )

    assert any("m4 did not participate" in c for c in result.caveats)
