"""Stage 4 — one final answer, guaranteed.

The synthesizer is a writer, not a second judge: the orchestrator has already resolved the
dispute. Feeding it the whole archive invites the three forbidden behaviours — blending
opposing positions into mush, resurrecting conceded claims, and re-litigating a settled
dispute — so the brief is sized to the rung. Rungs 0-3 need the winning position plus a
dissent summary; only rung 4, the one rung where it genuinely judges, earns the transcript.

Less context here is more *correct*, not merely cheaper. The full trace persists regardless:
storage for humans, curated brief for the model.
"""

from ..calls import Caller
from ..contracts import (
    DATA_RULE,
    DebateTurn,
    Dispute,
    Envelope,
    PanelAnswer,
    Rung,
    Stance,
    Verification,
    fence,
)
from ..contracts.wire import SynthesisOut
from ..ladder import LadderResult
from ..prompts.loader import fragment, render
from ..providers.base import ProviderError
from ..roles import ResolvedRole

_EXPLANATIONS = {
    Rung.UNANIMOUS: "every model reached the same conclusion; no material dispute was found",
    Rung.DEBATE: "a dispute was argued and one side conceded, citing what changed its mind",
    Rung.VERIFIED: "a disputed fact was checked against cited sources and the evidence decided it",
    Rung.MAJORITY: "argument did not settle it, so the position held by the most models wins",
    Rung.TIE_BREAK: "the panel split evenly, so the answer was chosen on visible evidence",
    Rung.FLOOR: "nothing distinguished the positions, so the designated default model's"
    " answer stands",
}


def _stance_text(stance: Stance, answers: list[PanelAnswer]) -> str:
    advocate = next((a for a in answers if a.model == stance.strongest), None)
    body = f"SUMMARY: {stance.summary}\n\n"
    if advocate:
        body += f"FULL ANSWER:\n{advocate.answer}"
    return body


def build_brief(
    result: LadderResult,
    *,
    stances: list[Stance],
    answers: list[PanelAnswer],
    disputes: list[Dispute],
    verifications: list[Verification],
    turns: list[DebateTurn],
) -> tuple[str, str]:
    winning = next((s for s in stances if s.id == result.winning_stance), None)
    if winning is None and stances:
        winning = stances[0]
    winning_text = (
        fence(fragment("brief_winning_header"), _stance_text(winning, answers))
        if winning
        else fence(fragment("brief_winning_header"), "(none identified)")
    )

    parts: list[str] = []

    dissenting = [s for s in stances if winning is None or s.id != winning.id]
    if dissenting:
        body = "\n\n".join(f"{s.id}: {s.summary}" for s in dissenting)
        parts.append(fence(fragment("brief_dissent_header"), body))

    evidence = [v for v in verifications if v.citations]
    if evidence:
        body = "\n\n".join(
            f"{v.dispute_id} [{v.outcome.value}]: {v.summary}\n"
            + "\n".join(f"  - {c.title or c.url} ({c.url})" for c in v.citations[:5])
            for v in evidence
        )
        parts.append(fence(fragment("brief_evidence_header"), body))

    branch_disputes = [d for d in disputes if d.id in result.branches]
    if branch_disputes:
        body = "\n\n".join(
            f"{d.question}\n"
            + "\n".join(f"  {sid}: {text}" for sid, text in sorted(d.positions.items()))
            for d in branch_disputes
        )
        parts.append(
fence(fragment("brief_branch_header"), body)
        )

    if result.rung is Rung.TIE_BREAK and turns:
        body = "\n\n".join(
            f"[{t.stance_id} r{t.round}] STEELMAN: {t.steelman}\nRESPONSE: {t.response}"
            for t in turns
        )
        parts.append(fence(fragment("brief_transcript_header"), body))

    if result.composition_check:
        parts.append(fragment("brief_coherence_check"))

    return winning_text, "\n\n".join(parts)


async def run(
    caller: Caller,
    role: ResolvedRole,
    envelope: Envelope,
    result: LadderResult,
    *,
    stances: list[Stance],
    answers: list[PanelAnswer],
    disputes: list[Dispute],
    verifications: list[Verification],
    turns: list[DebateTurn],
    timeout_s: float = 90.0,
) -> tuple[str, list[str], int]:
    winning_text, extra = build_brief(
        result,
        stances=stances,
        answers=answers,
        disputes=disputes,
        verifications=verifications,
        turns=turns,
    )
    prompt = render(
        role.prompt_version,
        data_rule=DATA_RULE,
        envelope=envelope.rendered(),
        rung_explanation=f"{result.resolution} — {_EXPLANATIONS[result.rung]}",
        winning=winning_text,
        extra=extra,
    )

    fallback = _fallback_answer(result, stances, answers)
    try:
        call = await caller.call(
            role=role.role.value,
            slug=role.slug,
            messages=[{"role": "user", "content": prompt}],
            prompt_version=role.prompt_version,
            out_model=SynthesisOut,
            schema_name="synthesis",
            temperature=role.temperature,
            fallback_slugs=role.fallbacks,
            timeout_s=timeout_s,
        )
    except ProviderError as exc:
        note = f"Synthesis failed ({exc}); the winning answer is reproduced verbatim."
        return fallback, [note], 0

    if call.parsed is None:
        return (
            fallback,
            ["Synthesis output could not be parsed; the winning answer is reproduced verbatim."],
            call.completion.usage.cost_micros,
        )

    out: SynthesisOut = call.parsed  # type: ignore[assignment]
    return out.final_answer, out.caveats, call.completion.usage.cost_micros


def _fallback_answer(
    result: LadderResult, stances: list[Stance], answers: list[PanelAnswer]
) -> str:
    """If synthesis fails, reproduce the winning answer verbatim rather than inventing one.

    The worst failure this product can have is a final answer containing a claim no model
    made, so the degraded path copies instead of writing.
    """
    winner = next((s for s in stances if s.id == result.winning_stance), None)
    target = result.winning_model or (winner.strongest if winner else None)
    answer = next((a for a in answers if a.model == target), None)
    if answer is None and answers:
        answer = answers[0]
    return answer.answer if answer else "No answer could be produced."
