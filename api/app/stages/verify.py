"""Stage 3a — grounded verification.

Two models arguing about a checkable fact is rhetoric versus rhetoric when the orchestrator
could just look. And a concession to evidence is the one kind of mind-changing that is
reliably legitimate, rather than trained-in agreeableness.

The rule that makes this honest is admissibility: grounding is model-discretionary, so a model
may answer from memory and return no citations. That response is an opinion in a lab coat and
is recorded as UNVERIFIABLE — never as `verified`. Rung 2 of the ladder is only reachable with
an artifact attached.

Retrieval is run once per position, framed toward each side in turn, for the same reason the
comparator is re-run with reversed order: framing is bias. If either framing finds support for
the other side, the outcome is CONFLICTING rather than whichever side we happened to ask about
first.
"""

import asyncio

from ..calls import Caller
from ..contracts import (
    DATA_RULE,
    Citation,
    Dispute,
    Verification,
    VerifyOutcome,
    fence,
)
from ..contracts.wire import VerificationOut
from ..prompts.loader import render
from ..providers.base import ProviderError
from ..roles import ResolvedRole


def citations_from(annotations: list[dict]) -> list[Citation]:
    """OpenRouter normalises every provider's native search into OpenAI-shaped
    `url_citation` annotations, so one parser covers Gemini grounding and the rest."""
    out: list[Citation] = []
    for item in annotations or []:
        if item.get("type") != "url_citation":
            continue
        cite = item.get("url_citation") or {}
        url = cite.get("url")
        if not url:
            continue
        out.append(
            Citation(
                url=url,
                title=cite.get("title") or "",
                snippet=(cite.get("content") or "")[:400],
                start_index=cite.get("start_index"),
                end_index=cite.get("end_index"),
            )
        )
    return out


def _positions_block(dispute: Dispute) -> str:
    lines = [f"{sid}: {text}" for sid, text in sorted(dispute.positions.items())]
    return fence("POSITIONS", "\n".join(lines))


async def _one_framing(
    caller: Caller,
    role: ResolvedRole,
    dispute: Dispute,
    focus: str,
    *,
    timeout_s: float,
) -> tuple[VerificationOut | None, list[Citation], str]:
    prompt = render(
        role.prompt_version,
        data_rule=DATA_RULE,
        question=fence("QUESTION", dispute.question),
        positions=_positions_block(dispute),
        query=dispute.search_query or dispute.question,
        focus=f"{focus}: {dispute.positions.get(focus, '')}",
    )
    try:
        call = await caller.call(
            role=role.role.value,
            slug=role.slug,
            messages=[{"role": "user", "content": prompt}],
            prompt_version=role.prompt_version,
            out_model=VerificationOut,
            schema_name="verification",
            web=True,
            timeout_s=timeout_s,
        )
    except ProviderError:
        return None, [], dispute.search_query or dispute.question

    return (
        call.parsed,  # type: ignore[return-value]
        citations_from(call.completion.annotations),
        dispute.search_query or dispute.question,
    )


async def run(
    caller: Caller,
    role: ResolvedRole,
    dispute: Dispute,
    *,
    timeout_s: float = 90.0,
) -> Verification:
    if not role.enabled:
        return Verification(
            dispute_id=dispute.id,
            outcome=VerifyOutcome.UNVERIFIABLE,
            summary="No grounded verifier is configured, so rung 2 is unavailable for this run.",
        )

    framings = list(dispute.positions.keys())[:2]
    results = await asyncio.gather(
        *(_one_framing(caller, role, dispute, focus, timeout_s=timeout_s) for focus in framings)
    )

    queries: list[str] = []
    citations: list[Citation] = []
    winners: set[str] = set()
    summaries: list[str] = []
    admissible_framings = 0

    for parsed, cites, query in results:
        queries.append(query)
        if parsed is None:
            continue
        summaries.append(parsed.summary)
        if not cites:
            # Answered without retrieving. Inadmissible: it carries no artifact.
            continue
        admissible_framings += 1
        citations.extend(cites)
        if parsed.outcome is VerifyOutcome.SUPPORTS and parsed.winning_stance:
            winners.add(parsed.winning_stance)

    summary = " | ".join(s for s in summaries if s)
    if admissible_framings == 0:
        return Verification(
            dispute_id=dispute.id,
            outcome=VerifyOutcome.UNVERIFIABLE,
            summary=summary or "No sources were retrieved, so nothing is verified.",
            queries=queries,
            citations=citations,
        )
    if len(winners) != 1:
        return Verification(
            dispute_id=dispute.id,
            outcome=VerifyOutcome.CONFLICTING,
            summary=summary
            or "Sources were retrieved but do not settle the question in either direction.",
            queries=queries,
            citations=citations,
        )

    note = "" if admissible_framings == 2 else " (only one framing retrieved sources)"
    return Verification(
        dispute_id=dispute.id,
        outcome=VerifyOutcome.SUPPORTS,
        winning_stance=next(iter(winners)),
        summary=summary + note,
        queries=queries,
        citations=citations,
    )
