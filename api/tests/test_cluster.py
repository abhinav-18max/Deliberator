"""The stance map must shrink only for reasons a machine can check."""

from conftest import action, stance, turn

from app.cluster import reduce_round, verify_concessions
from app.contracts import Action


def test_concession_folds_the_stance_and_moves_its_votes():
    stances = [stance("s1", ["m1"]), stance("s2", ["m2", "m3"])]
    turns = [turn("d1", "s2", "m2", [action("s1", Action.CONCEDE, withdrawn="claim one")])]

    result = reduce_round(stances, turns)

    assert result.surviving_ids == ["s1"]
    assert result.converged and result.winner == "s1"
    # The silent co-signer moves with its advocate rather than evaporating.
    assert set(result.stances[0].members) == {"m1", "m2", "m3"}
    assert result.concessions == [("s2", "s1")]


def test_mutual_concession_merges_rather_than_folding_either_side():
    stances = [stance("s1", ["m1"]), stance("s2", ["m2"])]
    turns = [
        turn("d1", "s1", "m1", [action("s2", Action.CONCEDE, withdrawn="a")]),
        turn("d1", "s2", "m2", [action("s1", Action.CONCEDE, withdrawn="b")]),
    ]

    result = reduce_round(stances, turns)

    assert result.surviving_ids == ["s1"]
    assert set(result.stances[0].members) == {"m1", "m2"}
    assert result.merges == [("s1", "s2")]
    assert result.concessions == []


def test_one_sided_revision_keeps_the_split():
    stances = [stance("s1", ["m1"]), stance("s2", ["m2"])]
    turns = [turn("d1", "s1", "m1", [action("s2", Action.REVISE, withdrawn="a")])]

    result = reduce_round(stances, turns)

    assert result.surviving_ids == ["s1", "s2"]
    assert not result.converged


def test_mutual_withdrawal_merges():
    stances = [stance("s1", ["m1"]), stance("s2", ["m2"])]
    turns = [
        turn("d1", "s1", "m1", [action("s2", Action.REVISE, withdrawn="a")]),
        turn("d1", "s2", "m2", [action("s1", Action.REVISE, withdrawn="b")]),
    ]

    result = reduce_round(stances, turns)

    assert result.converged
    assert set(result.stances[0].members) == {"m1", "m2"}


def test_chained_concessions_end_on_one_surviving_stance():
    stances = [stance("s1", ["m1"]), stance("s2", ["m2"]), stance("s3", ["m3"])]
    turns = [
        turn("d1", "s3", "m3", [action("s2", Action.CONCEDE, withdrawn="a")]),
        turn("d1", "s2", "m2", [action("s1", Action.CONCEDE, withdrawn="b")]),
    ]

    result = reduce_round(stances, turns)

    assert result.surviving_ids == ["s1"]
    assert set(result.stances[0].members) == {"m1", "m2", "m3"}


def test_defend_only_round_changes_nothing():
    stances = [stance("s1", ["m1"]), stance("s2", ["m2"])]
    turns = [
        turn("d1", "s1", "m1", [action("s2", Action.DEFEND)]),
        turn("d1", "s2", "m2", [action("s1", Action.DEFEND)]),
    ]

    result = reduce_round(stances, turns)

    assert result.surviving_ids == ["s1", "s2"]
    assert result.concessions == [] and result.merges == []


def test_concession_must_withdraw_a_claim_the_model_actually_made():
    claims = {"m2": ["token bucket absorbs bursts", "leaky bucket is smoother"]}
    def concede(withdrawn):
        return turn("d1", "s2", "m2", [action("s1", Action.CONCEDE, withdrawn=withdrawn)])

    good = concede("leaky bucket is smoother")
    invented = concede("something never said")
    empty = concede(None)

    assert verify_concessions([good], claims) == []
    assert verify_concessions([invented], claims) != []
    assert verify_concessions([empty], claims) != []
