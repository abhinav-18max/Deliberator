"""Stage 1 — independent answers in parallel.

Isolation is the whole basis of the product: independent judges only catch each other's
errors while their errors are independent. Models are already correlated by shared training
data; any peek at a peer adds anchoring and agreeableness on top, collapsing three opinions
into one opinion with three signatures.

A refusal is a dropout, never a stance. Otherwise the comparator dutifully discovers a
"material disagreement" between an answer and "I can't help with that".
"""

import asyncio
import re
from collections.abc import AsyncIterator

from ..calls import Caller
from ..contracts import DATA_RULE, Dropout, DropoutReason, Envelope, PanelAnswer
from ..contracts.wire import PanelAnswerOut
from ..prompts.loader import render
from ..providers.base import ProviderError, ProviderTimeout

_REFUSAL = re.compile(
    r"^\s*(i (?:can'?t|cannot|won'?t|am unable to|do not feel comfortable)|"
    r"i'?m (?:sorry|unable|not able)|as an ai|sorry,? (?:but )?i)",
    re.IGNORECASE,
)


def looks_like_refusal(text: str, finish_reason: str | None) -> bool:
    if finish_reason == "content_filter":
        return True
    stripped = (text or "").strip()
    # A refusal is short and front-loaded; a long answer that happens to open with a
    # hedge is not one.
    return bool(stripped) and len(stripped) < 400 and bool(_REFUSAL.match(stripped))


async def run(
    caller: Caller,
    envelope: Envelope,
    models: list[str],
    *,
    prompt_version: str = "panel_v1",
    timeout_s: float = 60.0,
) -> AsyncIterator[PanelAnswer | Dropout]:
    """Yields answers as they land, so the interface can show progress rather than a spinner."""
    prompt = render(prompt_version, data_rule=DATA_RULE, envelope=envelope.rendered())

    async def one(slug: str) -> PanelAnswer | Dropout:
        try:
            call = await caller.call(
                role="panel",
                slug=slug,
                messages=[{"role": "user", "content": prompt}],
                prompt_version=prompt_version,
                out_model=PanelAnswerOut,
                schema_name="panel_answer",
                timeout_s=timeout_s,
                skip_repair_if=lambda c: looks_like_refusal(c.text, c.finish_reason),
            )
        except ProviderTimeout as exc:
            return Dropout(model=slug, reason=DropoutReason.TIMEOUT, detail=str(exc))
        except (TimeoutError, ProviderError) as exc:
            return Dropout(model=slug, reason=DropoutReason.ERROR, detail=str(exc))

        completion = call.completion
        if looks_like_refusal(completion.text, completion.finish_reason):
            return Dropout(
                model=slug,
                reason=DropoutReason.REFUSAL,
                detail=completion.text[:200],
            )

        if call.parsed is None:
            # Structured output failed after one repair. The answer text is still usable;
            # the normalizer recovers the rest of the record downstream.
            if not completion.text.strip():
                return Dropout(model=slug, reason=DropoutReason.MALFORMED, detail="empty reply")
            return PanelAnswer(
                model=slug,
                answer=completion.text,
                normalized=False,
                latency_ms=completion.latency_ms,
                cost_micros=completion.usage.cost_micros,
            )

        out: PanelAnswerOut = call.parsed  # type: ignore[assignment]
        return PanelAnswer(
            model=slug,
            answer=out.answer,
            key_claims=out.key_claims,
            assumptions=out.assumptions,
            expected_consensus=out.expected_consensus,
            latency_ms=completion.latency_ms,
            cost_micros=completion.usage.cost_micros,
        )

    tasks = [asyncio.create_task(one(slug)) for slug in models]
    for finished in asyncio.as_completed(tasks):
        yield await finished
