"""Stage 3c — the debate machine, one per approach dispute.

Fully mediated: advocates never address each other, every prompt is composed here, and
opponents are identified only as positions. Names trigger measurable deference, and status
must not decide arguments.

One advocate per stance, facing all opposing positions in a single call. That costs k calls
per round instead of k(k-1)/2 duels, and it structurally cannot produce a circular pairwise
outcome because no pair is ever adjudicated.

Two rounds, because each round injects information the other side had not seen — round one
delivers the counter-argument, round two the counter-to-the-counter. A third recirculates
existing content, and from there the only active forces are verbosity and social pressure,
which models measurably capitulate to even when they were right.
"""

import asyncio
from collections.abc import AsyncIterator

from ..calls import Caller
from ..cluster import reduce_round, verify_concessions
from ..contracts import (
    DATA_RULE,
    Action,
    DebateTurn,
    Dispute,
    DisputeOutcome,
    Envelope,
    Mechanism,
    Stance,
    TurnAction,
    fence,
)
from ..contracts.wire import DebateTurnOut
from ..prompts.loader import fragment, render
from ..providers.base import ProviderError

RE_ASK = fragment("concession_reask")


def _own_block(stance: Stance, dispute: Dispute, claims: list[str]) -> str:
    position = dispute.positions.get(stance.id, stance.summary)
    body = f"POSITION: {position}\n\nYOUR ORIGINAL CLAIMS:\n"
    body += "\n".join(f"- {c}" for c in claims) or "- (none recorded)"
    return fence(fragment("debate_own_header"), body)


def _opposing_block(
    stance: Stance,
    dispute: Dispute,
    others: list[Stance],
    previous: dict[str, str] | None,
) -> str:
    blocks = []
    for other in others:
        if other.id == stance.id:
            continue
        if previous and other.id in previous:
            body = (
                f"POSITION: {dispute.positions.get(other.id, other.summary)}\n\n"
                f"THEIR RESPONSE TO YOU:\n{previous[other.id]}"
            )
        else:
            body = dispute.positions.get(other.id, other.summary)
        blocks.append(fence(f"POSITION {other.id}", body))
    return "\n\n".join(blocks)


async def _turn(
    caller: Caller,
    stance: Stance,
    dispute: Dispute,
    stances: list[Stance],
    envelope: Envelope,
    claims: list[str],
    *,
    rnd: int,
    previous: dict[str, str] | None,
    timeout_s: float,
    versions: tuple[str, str],
    extra_instruction: str = "",
) -> DebateTurn | None:
    version = versions[0] if rnd == 1 else versions[1]
    opponents = [s for s in stances if s.id != stance.id]
    prompt = render(
        version,
        data_rule=DATA_RULE,
        envelope=envelope.rendered(),
        own_position=_own_block(stance, dispute, claims),
        opposing=_opposing_block(stance, dispute, opponents, previous),
    )
    messages = [{"role": "user", "content": prompt}]
    if extra_instruction:
        messages.append({"role": "user", "content": extra_instruction})

    try:
        call = await caller.call(
            # A re-entrant panel seat, but accounted separately: the trace should show a
            # debate turn as a debate turn, not as another panel answer.
            role="debater",
            slug=stance.strongest,
            messages=messages,
            prompt_version=version,
            out_model=DebateTurnOut,
            schema_name="debate_turn",
            timeout_s=timeout_s,
        )
    except ProviderError:
        return None

    if call.parsed is None:
        # Conservative direction: an unparseable turn holds its ground. A parse failure must
        # never be able to fabricate a concession, because a fabricated concession closes a
        # live dispute and lands the answer on the strongest label in the system.
        return DebateTurn(
            dispute_id=dispute.id,
            round=rnd,
            stance_id=stance.id,
            model=stance.strongest,
            steelman="",
            response=call.completion.text[:4000],
            actions=[
                TurnAction(against_stance=o.id, action=Action.DEFEND) for o in opponents
            ],
            parse_degraded=True,
            cost_micros=call.completion.usage.cost_micros,
        )

    out: DebateTurnOut = call.parsed  # type: ignore[assignment]
    return DebateTurn(
        dispute_id=dispute.id,
        round=rnd,
        stance_id=stance.id,
        model=stance.strongest,
        steelman=out.steelman,
        response=out.response,
        actions=[
            TurnAction(
                against_stance=a.against_stance,
                action=a.action,
                because=a.because,
                withdrawn_claim=a.withdrawn_claim,
            )
            for a in out.actions
        ],
        cost_micros=call.completion.usage.cost_micros,
    )


def _downgrade_unbacked_concessions(turn: DebateTurn) -> DebateTurn:
    actions = [
        a
        if a.action is not Action.CONCEDE
        else TurnAction(
            against_stance=a.against_stance,
            action=Action.DEFEND,
            because="",
            withdrawn_claim=None,
        )
        for a in turn.actions
    ]
    return turn.model_copy(update={"actions": actions, "parse_degraded": True})


async def run(
    caller: Caller,
    envelope: Envelope,
    dispute: Dispute,
    stances: list[Stance],
    round0_claims: dict[str, list[str]],
    *,
    versions: tuple[str, str],
    max_rounds: int = 2,
    timeout_s: float = 90.0,
) -> AsyncIterator[DebateTurn | DisputeOutcome]:
    participants = [s for s in stances if s.id in dispute.positions]
    if len(participants) < 2:
        winner = participants[0].id if participants else None
        yield DisputeOutcome(
            dispute_id=dispute.id,
            mechanism=Mechanism.DEBATE,
            resolved=winner is not None,
            winning_stance=winner,
            rounds=0,
            note="only one stance held a position on this axis",
        )
        return

    current = participants
    previous: dict[str, str] | None = None

    for rnd in range(1, max_rounds + 1):
        results = await asyncio.gather(
            *(
                _turn(
                    caller,
                    stance,
                    dispute,
                    current,
                    envelope,
                    round0_claims.get(stance.strongest, []),
                    rnd=rnd,
                    previous=previous,
                    timeout_s=timeout_s,
                    versions=versions,
                )
                for stance in current
            )
        )
        turns = [t for t in results if t is not None]
        if not turns:
            break

        # Concession integrity: rejected once, re-asked, then held to DEFEND.
        unbacked = set(verify_concessions(turns, round0_claims))
        if unbacked:
            retried: list[DebateTurn] = []
            for turn in turns:
                key = f"{turn.dispute_id}:{turn.stance_id}:r{turn.round}"
                if key not in unbacked:
                    retried.append(turn)
                    continue
                again = await _turn(
                    caller,
                    next(s for s in current if s.id == turn.stance_id),
                    dispute,
                    current,
                    envelope,
                    round0_claims.get(turn.model, []),
                    rnd=rnd,
                    previous=previous,
                    timeout_s=timeout_s,
                    versions=versions,
                    extra_instruction=RE_ASK,
                )
                candidate = again or turn
                if verify_concessions([candidate], round0_claims):
                    candidate = _downgrade_unbacked_concessions(candidate)
                retried.append(candidate)
            turns = retried

        for turn in turns:
            yield turn

        result = reduce_round(current, turns)
        if result.converged:
            yield DisputeOutcome(
                dispute_id=dispute.id,
                mechanism=Mechanism.DEBATE,
                resolved=result.winner is not None,
                winning_stance=result.winner,
                rounds=rnd,
                note="closed by concession or merge",
            )
            return

        current = result.stances
        previous = {t.stance_id: t.response for t in turns}

    yield DisputeOutcome(
        dispute_id=dispute.id,
        mechanism=Mechanism.UNRESOLVED,
        resolved=False,
        rounds=max_rounds,
        note="both positions survived argument — an honest standoff, not a failure",
    )
