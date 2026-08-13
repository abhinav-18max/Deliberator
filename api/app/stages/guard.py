"""Stage 0 — the input boundary.

Nothing here calls a model, and that is the point. The task is wrapped, never rewritten:
if one strong model "improves" the task before fan-out, every panel model answers that
model's interpretation instead of the user's question, they agree with each other, and the
gate sees harmony. The system would fail silently in exactly the case it exists to catch.
"""

from ..contracts import Envelope
from ..contracts.request import DeliberateRequest
from ..roles import CapabilityIndex, ConfigError


def build_envelope(request: DeliberateRequest) -> Envelope:
    return Envelope(task=request.task, context=request.context)


def check_context_fit(
    envelope: Envelope,
    models: list[str],
    capabilities: CapabilityIndex | None,
    *,
    headroom_tokens: int = 2000,
) -> None:
    """The envelope must fit every panel model's window, or the selection is refused.

    Truncation that hits one model and not another manufactures a disagreement judgement
    never produced — and a manufactured MATERIAL verdict is worse than a missed one, because
    it is indistinguishable from a real finding.
    """
    if capabilities is None:
        return
    needed = envelope.approx_tokens() + headroom_tokens
    too_small = []
    for slug in models:
        limit = capabilities.context_length(slug)
        if limit is not None and limit < needed:
            too_small.append(f"{slug} (window {limit}, needs ~{needed})")
    if too_small:
        raise ConfigError(
            "the task and context do not fit every selected model's context window: "
            + "; ".join(too_small)
            + ". Truncating for some models only would fabricate a disagreement, so the "
            "selection is refused rather than silently degraded."
        )
