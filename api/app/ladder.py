"""The resolution ladder. Pure code, no I/O, no model.

Rungs are tried in order and the answer stops at the first that applies. The ordering is
the argument: voting sits *below* argument, because letting a wrong majority steamroll a
right minority before the minority can show them the missed constraint destroys the single
most valuable event this product exists to enable. Tie-breaks sit below voting, and a floor
guarantees the pipeline can never return "we couldn't decide".

Confidence is derived here, from how the answer won — never from a model's self-report,
which is documented as miscalibrated and flattery-shaped.
"""

from dataclasses import dataclass, field

from .contracts import (
    Confidence,
    DebateTurn,
    Dispute,
    DisputeOutcome,
    DissentKind,
    Dropout,
    Mechanism,
    PanelAnswer,
    ResolutionLabel,
    Rung,
    Stance,
    Verdict,
    Verification,
    VerifyOutcome,
)

_LABELS = {
    Rung.UNANIMOUS: ResolutionLabel.UNANIMOUS,
    Rung.DEBATE: ResolutionLabel.DEBATE_RESOLVED,
    Rung.VERIFIED: ResolutionLabel.VERIFIED,
    Rung.MAJORITY: ResolutionLabel.MAJORITY,
    Rung.TIE_BREAK: ResolutionLabel.TIE_BREAK,
    Rung.FLOOR: ResolutionLabel.FLOOR,
}

_DEMOTE = {
    Confidence.HIGH: Confidence.MEDIUM,
    Confidence.MEDIUM: Confidence.LOW,
    Confidence.LOW: Confidence.LOW,
}


@dataclass(frozen=True)
class LadderInput:
    verdict: Verdict
    stances: list[Stance]  # post-debate, after re-clustering
    disputes: list[Dispute]
    outcomes: list[DisputeOutcome]
    verifications: list[Verification]
    predictions: dict[str, str | None]
    answers: list[PanelAnswer]
    turns: list[DebateTurn]
    floor_model: str
    dropouts: list[Dropout] = field(default_factory=list)
    gate_validated: bool = True

    # Rigorous mode only: the text of a red-team attack that landed on a unanimous panel.
    # It cannot change who wins — nothing on the panel disagreed — but a consensus that a
    # fresh adversarial search could dent is not a high-confidence consensus.
    red_team_attack: str | None = None


@dataclass
class LadderResult:
    rung: Rung
    label: ResolutionLabel
    resolution: str
    confidence: Confidence
    winning_stance: str | None = None
    winning_model: str | None = None
    dissent: DissentKind | None = None
    tie_break_reason: str | None = None
    unresolved: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    composition_check: bool = False
    caveats: list[str] = field(default_factory=list)


def classify_dissent(
    stances: list[Stance], winning_stance: str | None, predictions: dict[str, str | None]
) -> DissentKind | None:
    """Informed dissent predicted the majority view and rejected it anyway — sometimes the
    minority that caught what everyone missed. Oblivious dissent expected everyone to agree
    with it and never engaged the mainstream at all. This never changes who wins; it only
    shapes the caveat and the confidence level."""
    if winning_stance is None:
        return None
    dissenters = [m for s in stances if s.id != winning_stance for m in s.members]
    if not dissenters:
        return None
    kinds = []
    for model in dissenters:
        predicted = predictions.get(model)
        if predicted is None:
            kinds.append(DissentKind.UNCLASSIFIABLE)
        elif predicted == winning_stance:
            kinds.append(DissentKind.INFORMED)
        else:
            kinds.append(DissentKind.OBLIVIOUS)
    if DissentKind.INFORMED in kinds:
        return DissentKind.INFORMED
    if all(k is DissentKind.UNCLASSIFIABLE for k in kinds):
        return DissentKind.UNCLASSIFIABLE
    return DissentKind.OBLIVIOUS


def _engagement_score(stance: Stance, turns: list[DebateTurn]) -> int:
    """Steelman fidelity is the most objective thing in the transcript, so it leads the
    tie-break. A turn that could not be parsed counts against the stance."""
    score = 0
    for turn in turns:
        if turn.stance_id != stance.id:
            continue
        if turn.parse_degraded:
            score -= 1
            continue
        if turn.steelman.strip():
            score += 1
        score += sum(1 for a in turn.actions if a.because.strip())
    return score


def _assumption_load(stance: Stance, answers: list[PanelAnswer]) -> float:
    counts = [len(a.assumptions) for a in answers if a.model in stance.members]
    return sum(counts) / len(counts) if counts else 0.0


def _informed_count(stance: Stance, predictions: dict[str, str | None]) -> int:
    return sum(
        1
        for m in stance.members
        if predictions.get(m) is not None and predictions.get(m) != stance.id
    )


def _unique_best(candidates: list[Stance], score) -> Stance | None:
    if not candidates:
        return None
    scored = sorted(candidates, key=score, reverse=True)
    best = score(scored[0])
    if len(scored) == 1 or score(scored[1]) < best:
        return scored[0]
    return None


def choose(inp: LadderInput) -> LadderResult:
    resolved = [o for o in inp.outcomes if o.resolved]
    branches = [o.dispute_id for o in inp.outcomes if o.mechanism is Mechanism.BRANCH]
    blocking = [
        o
        for o in inp.outcomes
        if not o.resolved and o.mechanism is not Mechanism.BRANCH
    ]
    questions = {d.id: d.question for d in inp.disputes}
    conflicting = [v for v in inp.verifications if v.outcome is VerifyOutcome.CONFLICTING]

    caveats: list[str] = []
    for o in blocking:
        caveats.append(
            f"Unresolved after {o.rounds} round(s): {questions.get(o.dispute_id, o.dispute_id)}."
            " Both positions survived argument."
        )
    for v in conflicting:
        caveats.append(
            f"Fact disputed and the public record did not settle it: "
            f"{questions.get(v.dispute_id, v.dispute_id)}."
        )
    for d in inp.dropouts:
        caveats.append(f"{d.model} did not participate ({d.reason}); the panel was smaller.")
    if any(t.parse_degraded for t in inp.turns):
        caveats.append(
            "A debate turn could not be parsed and was recorded as DEFEND, which keeps the"
            " dispute open rather than assuming a concession."
        )
    if not inp.gate_validated:
        caveats.append(
            "The comparator configuration is not in the verified registry, so the"
            " disagreement gate's reliability is unmeasured for this run."
        )
    if inp.red_team_attack:
        caveats.append(
            "The panel agreed, but an adversarial check found a standing objection: "
            f"{inp.red_team_attack}"
        )

    winners = {o.winning_stance for o in resolved if o.winning_stance}
    composition_check = len(winners) > 1

    def finish(
        rung: Rung,
        *,
        winning_stance: str | None = None,
        winning_model: str | None = None,
        resolution: str | None = None,
        tie_break_reason: str | None = None,
    ) -> LadderResult:
        dissent = classify_dissent(inp.stances, winning_stance, inp.predictions)
        confidence = _confidence(
            rung,
            dissent,
            sources_conflict=bool(conflicting),
            gate_validated=inp.gate_validated,
            red_team_landed=bool(inp.red_team_attack),
        )
        return LadderResult(
            rung=rung,
            label=_LABELS[rung],
            resolution=resolution or _LABELS[rung].value,
            confidence=confidence,
            winning_stance=winning_stance,
            winning_model=winning_model,
            dissent=dissent,
            tie_break_reason=tie_break_reason,
            unresolved=[o.dispute_id for o in blocking],
            branches=branches,
            composition_check=composition_check,
            caveats=caveats,
        )

    # Rung 0 — the gate found nothing that would change what the user does.
    if inp.verdict is not Verdict.MATERIAL:
        primary = inp.stances[0].id if inp.stances else None
        return finish(Rung.UNANIMOUS, winning_stance=primary)

    if not blocking:
        # Rung 1 — argument closed it. Rung 2 — evidence closed it.
        ordered = (
            (Mechanism.DEBATE, Rung.DEBATE),
            (Mechanism.VERIFICATION, Rung.VERIFIED),
        )
        for mechanism, rung in ordered:
            hit = next((o for o in resolved if o.mechanism is mechanism), None)
            if hit:
                return finish(rung, winning_stance=hit.winning_stance)

    # Rung 3 — majority, counted only now that argument has had its chance.
    total = sum(len(s.members) for s in inp.stances)
    if inp.stances:
        ranked = sorted(inp.stances, key=lambda s: len(s.members), reverse=True)
        top = len(ranked[0].members)
        if len(ranked) == 1 or len(ranked[1].members) < top:
            return finish(
                Rung.MAJORITY,
                winning_stance=ranked[0].id,
                resolution=f"majority ({top}/{total})",
            )

    # Rung 4 — tie-break on visible evidence, in fixed order, with the reason published.
    tied = inp.stances
    for reason, score in (
        (
            "quality of engagement in the debate transcript",
            lambda s: _engagement_score(s, inp.turns),
        ),
        ("fewer unstated assumptions", lambda s: -_assumption_load(s, inp.answers)),
        ("informed dissent over oblivious", lambda s: _informed_count(s, inp.predictions)),
    ):
        pick = _unique_best(tied, score)
        if pick is not None:
            return finish(Rung.TIE_BREAK, winning_stance=pick.id, tie_break_reason=reason)

    # Rung 5 — the floor. Structural guarantee of termination.
    holder = next((s for s in inp.stances if inp.floor_model in s.members), None)
    return finish(
        Rung.FLOOR,
        winning_stance=holder.id if holder else None,
        winning_model=inp.floor_model,
        resolution=f"floor ({inp.floor_model})",
    )


def _confidence(
    rung: Rung,
    dissent: DissentKind | None,
    *,
    sources_conflict: bool,
    gate_validated: bool,
    red_team_landed: bool = False,
) -> Confidence:
    if rung in (Rung.UNANIMOUS, Rung.DEBATE, Rung.VERIFIED):
        base = Confidence.HIGH
    elif rung is Rung.MAJORITY:
        base = Confidence.HIGH if dissent is DissentKind.OBLIVIOUS else Confidence.MEDIUM
    else:
        base = Confidence.LOW

    if sources_conflict:
        base = Confidence.LOW
    if red_team_landed:
        base = _DEMOTE[base]
    if not gate_validated:
        base = _DEMOTE[base]
    return base


def gate_failure(floor_model: str, reason: str) -> LadderResult:
    """The gate produced nothing usable, so no claim about agreement can be made.

    The honest response is the floor: return the designated default model's answer, labelled
    as such, at low confidence. Anything else would let a run with no comparison at all wear
    a label that implies one happened.
    """
    return LadderResult(
        rung=Rung.FLOOR,
        label=ResolutionLabel.FLOOR,
        resolution=f"floor ({floor_model})",
        confidence=Confidence.LOW,
        winning_model=floor_model,
        caveats=[
            f"The comparison stage failed ({reason}), so no agreement or disagreement was"
            " established. This is the designated default model's answer, unreviewed."
        ],
    )
