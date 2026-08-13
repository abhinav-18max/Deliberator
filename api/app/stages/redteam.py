"""Rigorous mode — attacking a unanimous consensus.

This is the only mechanism in the system that touches its acknowledged blind spot: if every
model shares an error, they agree, the gate stays quiet, and unanimous error looks exactly
like unanimous truth. Prompting a model to *break* an answer runs a different search over the
same knowledge than prompting it to *give* one. You cannot decorrelate the knowledge; you can
decorrelate the search.

Design deviation, deliberate and recorded: a landed attack is carried as a confidence
demotion plus a caveat rather than being opened as a synthetic dispute for debate. Making the
red team an advocate would give a model the user never selected a vote in rung 3's count, and
a non-panelist vote is not the panel's opinion. The attack still has to pass the same
materiality test as any organic dispute before it counts at all.
"""

from ..calls import Caller
from ..contracts import DATA_RULE, Envelope, Stance, fence
from ..contracts.wire import RedTeamOut
from ..prompts.loader import render
from ..providers.base import ProviderError
from ..roles import ResolvedRole


async def run(
    caller: Caller,
    role: ResolvedRole,
    envelope: Envelope,
    consensus: Stance,
    consensus_answer: str,
    *,
    timeout_s: float = 90.0,
) -> tuple[RedTeamOut | None, int]:
    if not role.enabled:
        return None, 0

    prompt = render(
        role.prompt_version,
        data_rule=DATA_RULE,
        envelope=envelope.rendered(),
        consensus=fence(
            "AGREED POSITION", f"SUMMARY: {consensus.summary}\n\nANSWER:\n{consensus_answer}"
        ),
    )
    try:
        call = await caller.call(
            role=role.role.value,
            slug=role.slug,
            messages=[{"role": "user", "content": prompt}],
            prompt_version=role.prompt_version,
            out_model=RedTeamOut,
            schema_name="red_team",
            fallback_slugs=role.fallbacks,
            timeout_s=timeout_s,
        )
    except ProviderError:
        return None, 0

    cost = call.completion.usage.cost_micros
    if call.parsed is None:
        return None, cost

    out: RedTeamOut = call.parsed  # type: ignore[assignment]
    # The materiality test applies to the red team exactly as it does to the comparator: an
    # attack that cannot say what the user would do differently has not landed.
    if not out.lands or not (out.decision_impact or "").strip():
        return None, cost
    return out, cost
