"""Comparator regression harness.

The NONE/SURFACE/MATERIAL boundary is the one judgement the system cannot self-correct: a
missed MATERIAL verdict silently disables the entire product and nothing downstream can detect
it. So this is the one judgement tuned against data instead of intuition.

The metric is deliberately asymmetric. **MATERIAL recall must be 1.0** — every real
disagreement has to fire — and precision is reported separately, because a false MATERIAL costs
a few model calls while a false NONE costs the product's reason to exist. Accuracy would average
those two very different failures into one meaningless number.

Runs against recorded completions, so a re-run is free and offline. Also reports the
SURFACE/NONE confusion separately: those two are a presentation distinction, not a safety one,
and conflating them is not a defect worth chasing.
"""

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from ..calls import Caller
from ..contracts import PanelAnswer, Verdict
from ..contracts.envelope import Envelope
from ..providers.openrouter import OpenRouterProvider
from ..providers.replay import CachingProvider
from ..roles import Role, RoleRegistry
from ..settings import load_config, load_settings
from ..stages import compare
from ..store.memory import MemoryStore

CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass
class Outcome:
    case_id: str
    expected: str
    actual: str | None
    stances: int
    disputes: int
    types: list[str]

    @property
    def passed(self) -> bool:
        return self.actual == self.expected

    @property
    def safe(self) -> bool:
        """A real disagreement fired. The only failure mode that cannot be recovered."""
        if self.expected != Verdict.MATERIAL.value:
            return True
        return self.actual == Verdict.MATERIAL.value


def load_cases(version: str = "comparator_v1") -> list[dict]:
    return json.loads((CASES_DIR / f"{version}.json").read_text())


async def run_case(caller: Caller, role, case: dict) -> Outcome:
    answers = [
        PanelAnswer(
            model=a["model"],
            answer=a["answer"],
            key_claims=a.get("key_claims", []),
            assumptions=a.get("assumptions", []),
            expected_consensus=a.get("expected_consensus"),
        )
        for a in case["answers"]
    ]
    envelope = Envelope(task=case["task"], context=case.get("context"))
    # Order is seeded by the case id, so a case presents identically on every run.
    order = compare.presentation_order(case["id"], len(answers))
    result = await compare.run(caller, role, envelope, answers, order=order)
    return Outcome(
        case_id=case["id"],
        expected=case["label"],
        actual=result.verdict.value if result else None,
        stances=len(result.stances) if result else 0,
        disputes=len(result.disputes) if result else 0,
        types=sorted({d.type.value for d in result.disputes}) if result else [],
    )


async def main() -> int:
    settings = load_settings()
    cfg = load_config()
    store = MemoryStore()

    # Recorded completions live in Mongo when it is configured, so the second run is free.
    if settings.has_mongo:
        from ..store.mongo import MongoStore

        store = MongoStore(settings.mongodb_uri, settings.mongodb_db)  # type: ignore[assignment]
        await store.ensure_ready()

    live = OpenRouterProvider(settings) if settings.openrouter_api_key else None
    provider = CachingProvider(store, inner=live)
    caller = Caller(provider)
    role = RoleRegistry(cfg).resolve(Role.COMPARATOR, panel=[])

    cases = load_cases(role.prompt_version)
    outcomes = await asyncio.gather(*(run_case(caller, role, case) for case in cases))

    material = [o for o in outcomes if o.expected == Verdict.MATERIAL.value]
    fired = [o for o in outcomes if o.actual == Verdict.MATERIAL.value]
    true_positive = [o for o in material if o.actual == Verdict.MATERIAL.value]
    missed = [o for o in material if o.actual != Verdict.MATERIAL.value]
    false_positive = [o for o in fired if o.expected != Verdict.MATERIAL.value]

    recall = len(true_positive) / len(material) if material else 1.0
    precision = len(true_positive) / len(fired) if fired else 1.0

    print(f"comparator: {role.slug} / {role.prompt_version}")
    print(f"cases: {len(outcomes)}  (recorded {provider.hits}, live {provider.misses})\n")
    for o in sorted(outcomes, key=lambda x: (x.safe, x.passed, x.case_id)):
        mark = "ok  " if o.passed else ("MISS" if not o.safe else "soft")
        types = f" types={','.join(o.types)}" if o.types else ""
        print(
            f"  [{mark}] {o.case_id:<38} expected={o.expected:<8} got={o.actual or 'unparsed':<8}"
            f" stances={o.stances} disputes={o.disputes}{types}"
        )

    print()
    print(f"MATERIAL recall    {recall:.2f}   ({len(true_positive)}/{len(material)})")
    print(f"MATERIAL precision {precision:.2f}   ({len(true_positive)}/{len(fired)})")
    if missed:
        print("\nMissed disagreements — these are the only failures that matter:")
        for o in missed:
            print(f"  - {o.case_id}: said {o.actual}")
    if false_positive:
        print("\nOver-fired (billed, not dangerous):")
        for o in false_positive:
            print(f"  - {o.case_id}: expected {o.expected}, said material")

    exact = sum(1 for o in outcomes if o.passed)
    print(f"\nexact label match  {exact}/{len(outcomes)}")

    if recall >= 1.0:
        print(
            "\nRecall is 1.0 — add this pair to `verified_configs` in config.yaml:\n"
            f"  - slug: {role.slug}\n"
            f"    prompt_version: {role.prompt_version}\n"
            f"    material_recall: {recall:.2f}"
        )
    if live:
        await live.aclose()
    closer = getattr(store, "close", None)
    if closer:
        await closer()
    return 0 if recall >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
