"""Re-clustering between debate rounds. Pure code, no I/O, no model.

The stance map should shrink toward resolution: a three-way debate usually becomes a
two-way debate after round one, making round two both cheaper and sharper. Only two
transitions are mechanical enough to be trusted here:

*   **Concession folds a stance.** Its members — the silent co-signers — move with their
    advocate, so votes transfer rather than evaporating.
*   **Mutual withdrawal merges two stances.** If both sides withdraw a claim of their own
    in the other's favour, they have converged on something neither started with. One-sided
    revision does *not* merge: that is still a split, and pretending otherwise would
    manufacture consensus.

Judging whether two revised positions are "compatible" in general is a semantic call and
deliberately not attempted here. See DESIGN.md limitations.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .contracts import Action, DebateTurn, Stance


@dataclass
class RoundResult:
    stances: list[Stance]
    surviving_ids: list[str]
    concessions: list[tuple[str, str]] = field(default_factory=list)  # (from, to)
    merges: list[tuple[str, str]] = field(default_factory=list)  # (a, b)

    @property
    def converged(self) -> bool:
        return len(self.surviving_ids) <= 1

    @property
    def winner(self) -> str | None:
        return self.surviving_ids[0] if len(self.surviving_ids) == 1 else None


class _Union:
    def __init__(self, ids: Iterable[str]) -> None:
        self._parent = {i: i for i in ids}

    def find(self, a: str) -> str:
        while self._parent[a] != a:
            self._parent[a] = self._parent[self._parent[a]]
            a = self._parent[a]
        return a

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Lower id wins so the outcome is order-independent and reproducible.
            root, other = sorted((ra, rb))
            self._parent[other] = root


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def reduce_round(stances: list[Stance], turns: list[DebateTurn]) -> RoundResult:
    """Fold the stance map given one round of turns."""
    by_id = {s.id: s for s in stances}
    live = [s.id for s in stances]

    concedes: set[tuple[str, str]] = set()
    withdraws: set[tuple[str, str]] = set()
    for turn in turns:
        if turn.stance_id not in by_id:
            continue
        for action in turn.actions:
            if action.against_stance not in by_id:
                continue
            pair = (turn.stance_id, action.against_stance)
            if action.action is Action.CONCEDE:
                concedes.add(pair)
            elif action.action is Action.REVISE and action.withdrawn_claim:
                withdraws.add(pair)

    # Mutual moves are merges, not folds: nobody can fold into someone who folded into them.
    merge_pairs = {
        tuple(sorted(p))
        for p in concedes | withdraws
        if (p[1], p[0]) in (concedes | withdraws)
    }
    union = _Union(live)
    for a, b in merge_pairs:
        union.union(a, b)

    folds = [p for p in sorted(concedes) if tuple(sorted(p)) not in merge_pairs]

    members: dict[str, list[str]] = {sid: list(by_id[sid].members) for sid in live}
    strongest: dict[str, str] = {sid: by_id[sid].strongest for sid in live}
    summaries: dict[str, str] = {sid: by_id[sid].summary for sid in live}

    # Collapse merge groups onto their root.
    for sid in list(live):
        root = union.find(sid)
        if root == sid:
            continue
        members[root] = _dedupe(members[root] + members[sid])
        summaries[root] = f"{summaries[root]} / {summaries[sid]}"
        members.pop(sid, None)

    # Then apply one-way concessions. A stance that has already folded is not a valid
    # destination, so both ends are chased through earlier folds first — otherwise a
    # concession chain (s3 -> s2 -> s1) would leave s3 stranded as a live stance.
    redirect: dict[str, str] = {}

    def surviving_target(sid: str) -> str:
        current = union.find(sid)
        seen: set[str] = set()
        while current in redirect and current not in seen:
            seen.add(current)
            current = union.find(redirect[current])
        return current

    concessions: list[tuple[str, str]] = []
    for src, dst in folds:
        src_root, dst_root = surviving_target(src), surviving_target(dst)
        if src_root == dst_root or src_root not in members or dst_root not in members:
            continue
        members[dst_root] = _dedupe(members[dst_root] + members[src_root])
        members.pop(src_root)
        redirect[src_root] = dst_root
        concessions.append((src, dst))

    surviving = [sid for sid in live if sid in members]
    result_stances = [
        Stance(
            id=sid,
            summary=summaries[sid],
            members=members[sid],
            strongest=(
                strongest[sid] if strongest[sid] in members[sid] else members[sid][0]
            ),
        )
        for sid in surviving
    ]
    return RoundResult(
        stances=result_stances,
        surviving_ids=surviving,
        concessions=concessions,
        merges=[(a, b) for a, b in sorted(merge_pairs)],
    )


def verify_concessions(turns: list[DebateTurn], round0_claims: dict[str, list[str]]) -> list[str]:
    """Return ids of turns whose concession is not backed by a claim the model actually
    made in round 0.

    A concession has to cost the conceder something specific. Empty polite capitulation is
    trained-in behaviour, and if it were accepted it could close a live dispute and land
    the answer on rung 1 — the strongest label in the system — for free.
    """
    invalid: list[str] = []
    for turn in turns:
        claims = {c.strip().lower() for c in round0_claims.get(turn.model, [])}
        for action in turn.actions:
            if action.action is not Action.CONCEDE:
                continue
            claim = (action.withdrawn_claim or "").strip().lower()
            if not claim or (claims and claim not in claims):
                invalid.append(f"{turn.dispute_id}:{turn.stance_id}:r{turn.round}")
                break
    return invalid
