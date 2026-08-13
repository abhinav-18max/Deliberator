"""Stage 2 — the gate.

Three of the judge biases this stage is exposed to are handled here rather than hoped away:

*   **verbosity bias** — the comparator reads the claims list first, so all inputs arrive in
    the same size and shape and the wordiest panelist does not win by volume.
*   **self-preference** — answers are labelled `A`, `B`, `C`, never named, and the labels are
    translated back to slugs after the call.
*   **position bias** — presentation order is shuffled deterministically per run, and in
    rigorous mode the whole call is repeated with the order reversed. A verdict that flips is
    treated as MATERIAL: uncertainty about whether there is a disagreement is a disagreement.

This stage is the pipeline's single point of failure, which is why it alone gets an eval set.
"""

import hashlib
from dataclasses import dataclass

from ..calls import Caller
from ..contracts import (
    DATA_RULE,
    Comparison,
    Dispute,
    Envelope,
    PanelAnswer,
    Stance,
    Verdict,
    fence,
)
from ..contracts.wire import ComparisonOut
from ..prompts.loader import fragment, render
from ..roles import ResolvedRole

_LABELS = "ABCDEFGH"


def presentation_order(seed: str, count: int) -> list[int]:
    """Deterministic for a given seed, so a trace replays identically, but not a fixed bias.

    The orchestrator seeds this from the envelope and panel rather than the run id, so the same
    task presents the same way every time and recorded completions stay valid across runs.
    """
    digest = hashlib.sha256(seed.encode()).digest()
    indices = list(range(count))
    # Fisher-Yates driven by the digest: reproducible without a global RNG.
    for i in range(count - 1, 0, -1):
        j = digest[i % len(digest)] % (i + 1)
        indices[i], indices[j] = indices[j], indices[i]
    return indices


@dataclass
class Presentation:
    text: str
    label_to_slug: dict[str, str]


def present(answers: list[PanelAnswer], order: list[int]) -> Presentation:
    blocks: list[str] = []
    mapping: dict[str, str] = {}
    for position, index in enumerate(order):
        answer = answers[index]
        label = _LABELS[position]
        mapping[label] = answer.model
        claims = "\n".join(f"- {c}" for c in answer.key_claims) or "- (none stated)"
        assumptions = "\n".join(f"- {a}" for a in answer.assumptions) or "- (none stated)"
        body = (
            f"KEY CLAIMS:\n{claims}\n\n"
            f"DECLARED ASSUMPTIONS:\n{assumptions}\n\n"
            f"EXPECTED CONSENSUS: {answer.expected_consensus or '(not given)'}\n\n"
            f"FULL ANSWER:\n{answer.answer}"
        )
        blocks.append(fence(f"ANSWER {label}", body))
    return Presentation(text="\n\n".join(blocks), label_to_slug=mapping)


def assumption_divergence(answers: list[PanelAnswer]) -> list[str]:
    """The cheapest disagreement detector in the system, and it runs before any judgement.

    If one model assumed Postgres and another assumed MySQL, they answered different
    questions — and interpretation differences are the dangerous kind precisely because each
    answer looks internally perfect.
    """
    if len(answers) < 2:
        return []
    sets = {a.model: {s.strip().lower() for s in a.assumptions if s.strip()} for a in answers}
    shared = set.intersection(*sets.values()) if sets else set()
    unique: list[str] = []
    for model, values in sets.items():
        only = values - shared
        if only:
            unique.append(f"{model} alone assumed: {'; '.join(sorted(only))}")
    return unique


def _translate(out: ComparisonOut, mapping: dict[str, str]) -> Comparison:
    def slug(label: str) -> str:
        return mapping.get(label, label)

    stances = [
        Stance(
            id=s.id,
            summary=s.summary,
            members=[slug(m) for m in s.members],
            strongest=slug(s.strongest),
        )
        for s in out.stances
    ]
    disputes = [
        Dispute(
            id=d.id,
            type=d.type,
            question=d.question,
            decision_impact=d.decision_impact,
            positions={p.stance_id: p.position for p in d.positions},
            search_query=d.search_query,
        )
        for d in out.disputes
    ]
    predictions = {slug(p.model_slug): p.stance_id for p in out.predictions}
    return Comparison(
        verdict=out.verdict,
        justification=out.justification,
        stances=stances,
        disputes=disputes,
        predictions=predictions,
    )


async def run(
    caller: Caller,
    role: ResolvedRole,
    envelope: Envelope,
    answers: list[PanelAnswer],
    *,
    order: list[int],
    timeout_s: float = 90.0,
) -> Comparison | None:
    presentation = present(answers, order)
    divergence = assumption_divergence(answers)
    hint = (
        "\n\n"
        + fragment("assumption_divergence")
        + "\n"
        + "\n".join(f"- {d}" for d in divergence)
        if divergence
        else ""
    )
    prompt = render(
        role.prompt_version,
        data_rule=DATA_RULE,
        envelope=envelope.rendered(),
        answers=presentation.text + hint,
    )
    call = await caller.call(
        role=role.role.value,
        slug=role.slug,
        messages=[{"role": "user", "content": prompt}],
        prompt_version=role.prompt_version,
        out_model=ComparisonOut,
        schema_name="comparison",
        temperature=role.temperature,
        fallback_slugs=role.fallbacks,
        timeout_s=timeout_s,
    )
    if call.parsed is None:
        return None
    try:
        return _translate(call.parsed, presentation.label_to_slug)  # type: ignore[arg-type]
    except ValueError:
        # A dispute that fails its own materiality or checkability test is rejected by the
        # contract. The gate produced something unusable; the caller decides what that means.
        return None


def merge_reversed(first: Comparison, second: Comparison | None) -> Comparison:
    """Rigorous mode: a verdict that changes when the order changes is itself a disagreement."""
    if second is None or first.verdict == second.verdict:
        return first
    stronger = max((first, second), key=lambda c: (c.verdict is Verdict.MATERIAL, len(c.disputes)))
    # Only one of these two runs can be promoted to MATERIAL, because a MATERIAL verdict has
    # to carry extracted disputes — instability alone gives us nothing to debate. When
    # neither pass found disputes, the flag and the caveat are the honest output.
    consequence = (
        "treated as material"
        if stronger.verdict is Verdict.MATERIAL
        else "no dispute was extractable in either pass, so the stronger verdict stands and "
        "the instability is carried as a caveat"
    )
    return stronger.model_copy(
        update={
            "unstable": True,
            "justification": (
                f"{stronger.justification} [Order-reversed re-run disagreed "
                f"({first.verdict.value} vs {second.verdict.value}); {consequence}.]"
            ),
        }
    )
