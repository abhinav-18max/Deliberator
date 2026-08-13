"""Stage 3a — grounded verification.

Two models arguing about a checkable fact is rhetoric versus rhetoric when the orchestrator
could just look. And a concession to evidence is the one kind of mind-changing that is
reliably legitimate, rather than trained-in agreeableness.

The rule that makes this honest is admissibility, and it has two halves:

1.  Sources must have been retrieved. A model answering from parametric memory returns no
    citations, and that response is an opinion in a lab coat — recorded UNVERIFIABLE, never
    `verified`.
2.  The verifier must name which retrieved sources carry its verdict, and every named URL must
    be one that was actually retrieved. This half exists because retrieval is performed by the
    gateway: annotations are then always present, so their presence alone stops proving the
    model used them. A URL the model produces that was never fetched is a fabricated citation,
    and it invalidates the result rather than decorating it.

Rung 2 of the ladder is reachable only with both halves satisfied.

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
    """OpenRouter normalises both retrieval engines into OpenAI-shaped `url_citation`
    annotations, so one parser covers gateway search and provider-native grounding alike."""
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
            web_engine=role.search_engine,
            temperature=role.temperature,
            fallback_slugs=role.fallbacks,
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
    supporting: list[str] = []
    admissible_framings = 0
    fabricated: list[str] = []

    for parsed, cites, query in results:
        queries.append(query)
        if parsed is None:
            continue
        summaries.append(parsed.summary)
        if not cites:
            # Answered without retrieving. Inadmissible: it carries no artifact.
            continue
        retrieved = {c.url for c in cites}
        named = [u for u in parsed.supporting_urls if u]
        invented = [u for u in named if u not in retrieved]
        if invented:
            # A citation that was never fetched is fabricated. Discard the whole framing
            # rather than keeping the half of it that happens to check out.
            fabricated.extend(invented)
            continue
        if not named:
            continue
        admissible_framings += 1
        citations.extend(cites)
        supporting.extend(named)
        if parsed.outcome is VerifyOutcome.SUPPORTS and parsed.winning_stance:
            winners.add(parsed.winning_stance)

    summary = " | ".join(s for s in summaries if s)
    if fabricated:
        summary += (
            f" [Discarded a framing that cited {len(fabricated)} source(s) never retrieved.]"
        )
    if admissible_framings == 0:
        return Verification(
            dispute_id=dispute.id,
            outcome=VerifyOutcome.UNVERIFIABLE,
            summary=summary
            or "No admissible sources came back, so nothing is verified.",
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
            supporting_urls=sorted(set(supporting)),
        )

    note = "" if admissible_framings == 2 else " (only one framing retrieved sources)"
    return Verification(
        dispute_id=dispute.id,
        outcome=VerifyOutcome.SUPPORTS,
        winning_stance=next(iter(winners)),
        summary=summary + note,
        queries=queries,
        citations=citations,
        supporting_urls=sorted(set(supporting)),
    )
