"""Repair path for a panel model that returned prose instead of the record.

OpenRouter's structured-output support is per-endpoint, not per-model, so a caller-selected
model may ignore the schema entirely. Recovering the record with a trusted extractive call
keeps the comparator's input uniform without trusting the weak model's formatting.

`expected_consensus` is the one field that cannot be recovered honestly. Asked after the fact
it would be hindsight, and invented here it would corrupt the confidence level — so a missing
prediction stays missing and that model's dissent is later recorded as unclassifiable.
"""

from ..calls import Caller
from ..contracts import DATA_RULE, PanelAnswer, fence
from ..contracts.wire import NormalizerOut
from ..prompts.loader import render
from ..providers.base import ProviderError
from ..roles import ResolvedRole


async def recover(
    caller: Caller, role: ResolvedRole, answer: PanelAnswer, *, timeout_s: float = 90.0
) -> PanelAnswer:
    if not role.enabled:
        return answer

    prompt = render(
        role.prompt_version,
        data_rule=DATA_RULE,
        answer=fence("ANSWER", answer.answer),
    )
    try:
        call = await caller.call(
            role=role.role.value,
            slug=role.slug,
            messages=[{"role": "user", "content": prompt}],
            prompt_version=role.prompt_version,
            out_model=NormalizerOut,
            schema_name="normalizer",
            temperature=role.temperature,
            fallback_slugs=role.fallbacks,
            timeout_s=timeout_s,
        )
    except ProviderError:
        return answer

    if call.parsed is None:
        return answer

    out: NormalizerOut = call.parsed  # type: ignore[assignment]
    return answer.model_copy(
        update={
            "key_claims": out.key_claims,
            "assumptions": out.assumptions,
            "expected_consensus": out.expected_consensus,
            "normalized": True,
            "cost_micros": answer.cost_micros + call.completion.usage.cost_micros,
        }
    )
