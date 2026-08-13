"""Checks that a run's published label is justified by its own event tape.

The resolution label is the product's honesty contract: it is the only thing stopping a
floor-rung answer from impersonating a unanimous one. A contract nobody checks is a hope, so
this re-derives every published claim from the tape and reports anything the record does not
support.

It is pure and runs over stored events, which means it works three ways: as a CI assertion on
every pipeline test, as a command against any persisted run, and as a review tool on a trace
someone hands you. It deliberately does not trust the FinalAnswer's own numbers — recomputing
confidence from the tape is what would catch a drift between what the ladder decided and what
the response advertised.
"""

import re
import sys
from dataclasses import dataclass

from .contracts import (
    Confidence,
    DissentKind,
    EventType,
    Mechanism,
    ResolutionLabel,
    Rung,
    TraceEvent,
    Verdict,
    VerifyOutcome,
)
from .ladder import _confidence

_EXPECTED_LABEL = {
    Rung.UNANIMOUS: ResolutionLabel.UNANIMOUS,
    Rung.DEBATE: ResolutionLabel.DEBATE_RESOLVED,
    Rung.VERIFIED: ResolutionLabel.VERIFIED,
    Rung.MAJORITY: ResolutionLabel.MAJORITY,
    Rung.TIE_BREAK: ResolutionLabel.TIE_BREAK,
    Rung.FLOOR: ResolutionLabel.FLOOR,
}

_WORD = re.compile(r"[^a-z0-9 ]+")


def _normalise(text: str) -> str:
    return _WORD.sub(" ", (text or "").lower()).strip()


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


def validate(events: list[TraceEvent]) -> list[Violation]:  # noqa: C901 — one rule per branch
    out: list[Violation] = []
    by_type: dict[EventType, list[dict]] = {}
    for event in events:
        by_type.setdefault(event.type, []).append(event.payload)

    finals = by_type.get(EventType.RUN_FINAL, [])
    if not finals:
        # A run that errored before finalising is not a contract violation.
        if not by_type.get(EventType.RUN_ERROR):
            out.append(Violation("terminates", "no run.final and no run.error on the tape"))
        return out
    final = finals[-1]

    rung = Rung(int(final["rung"]))
    label = ResolutionLabel(final["label"])
    verdict = by_type.get(EventType.COMPARE_VERDICT, [{}])
    closed = by_type.get(EventType.DISPUTE_CLOSED, [])
    verifications = by_type.get(EventType.VERIFY_RESULT, [])
    turns = by_type.get(EventType.DEBATE_TURN, [])
    calls = by_type.get(EventType.MODEL_CALL, [])
    rung_events = by_type.get(EventType.LADDER_RUNG, [])

    # --- the label must match the rung it claims -------------------------------------
    if label is not _EXPECTED_LABEL[rung]:
        out.append(
            Violation("label-matches-rung", f"rung {int(rung)} published as {label.value}")
        )

    # --- each rung requires specific evidence on the tape ---------------------------
    resolved_by = {
        Mechanism(c["mechanism"]) for c in closed if c.get("resolved") and c.get("mechanism")
    }

    if rung is Rung.UNANIMOUS:
        if not verdict[0]:
            out.append(Violation("unanimous-needs-gate", "no compare.verdict on the tape"))
        elif Verdict(verdict[0]["verdict"]) is Verdict.MATERIAL:
            out.append(
                Violation(
                    "unanimous-needs-gate",
                    "claimed unanimous while the gate returned a material verdict",
                )
            )
        if turns:
            out.append(
                Violation("unanimous-has-no-debate", f"{len(turns)} debate turn(s) recorded")
            )

    if rung is Rung.DEBATE and Mechanism.DEBATE not in resolved_by:
        out.append(
            Violation(
                "debate-needs-a-closure",
                "claimed debate-resolved with no dispute closed by debate",
            )
        )

    if rung is Rung.VERIFIED:
        if Mechanism.VERIFICATION not in resolved_by:
            out.append(
                Violation(
                    "verified-needs-a-closure",
                    "claimed verified with no dispute closed by verification",
                )
            )
        admissible = [
            v
            for v in verifications
            if VerifyOutcome(v["outcome"]) is VerifyOutcome.SUPPORTS
            and v.get("citations")
            and v.get("supporting_urls")
        ]
        if not admissible:
            out.append(
                Violation(
                    "verified-needs-an-artifact",
                    "claimed verified with no citation-backed verification — this label may "
                    "not be reached by a model answering from memory",
                )
            )

    if rung in (Rung.MAJORITY, Rung.TIE_BREAK, Rung.FLOOR) and resolved_by & {
        Mechanism.DEBATE,
        Mechanism.VERIFICATION,
    }:
        # Voting sits below argument. If argument or evidence settled it, a lower rung is a
        # demotion the tape does not justify.
        out.append(
            Violation(
                "voting-sits-below-argument",
                f"rung {int(rung)} taken although a dispute was resolved by "
                f"{', '.join(sorted(m.value for m in resolved_by))}",
            )
        )

    if rung is Rung.TIE_BREAK and not final.get("tie_break_reason"):
        out.append(Violation("tie-break-is-published", "tie-break taken with no reason given"))

    # --- confidence is derived, not asserted ---------------------------------------
    conflicting = any(
        VerifyOutcome(v["outcome"]) is VerifyOutcome.CONFLICTING for v in verifications
    )
    red_team_landed = any(
        "adversarial check found a standing objection" in c for c in final.get("caveats", [])
    )
    dissent = DissentKind(final["dissent"]) if final.get("dissent") else None
    expected = _confidence(
        rung,
        dissent,
        sources_conflict=conflicting,
        gate_validated=bool(final.get("gate_validated", True)),
        red_team_landed=red_team_landed,
    )
    if Confidence(final["confidence"]) is not expected:
        out.append(
            Violation(
                "confidence-is-derived",
                f"published {final['confidence']} but the tape derives {expected.value} "
                f"(rung {int(rung)}, dissent {dissent.value if dissent else 'none'}, "
                f"conflicting sources {conflicting}, gate validated "
                f"{final.get('gate_validated')})",
            )
        )
    if rung_events and rung_events[-1]["confidence"] != final["confidence"]:
        out.append(
            Violation(
                "confidence-does-not-drift",
                f"ladder recorded {rung_events[-1]['confidence']}, response published "
                f"{final['confidence']}",
            )
        )

    # --- surviving disagreement has to be admitted --------------------------------
    if final.get("unresolved_disputes") and not final.get("caveats"):
        out.append(
            Violation(
                "dissent-is-named",
                "unresolved disputes recorded but no caveat mentions them",
            )
        )

    # --- a conceded claim may not reappear in the answer --------------------------
    answer = _normalise(final["final_answer"])
    for turn in turns:
        for action in turn.get("actions", []):
            claim = action.get("withdrawn_claim")
            if action.get("action") != "concede" or not claim:
                continue
            normalised = _normalise(claim)
            # Only long claims are checked: short fragments collide with ordinary prose and
            # would make this rule noisy rather than useful.
            if len(normalised) > 30 and normalised in answer:
                out.append(
                    Violation(
                        "conceded-claims-stay-dead",
                        f"the answer repeats a claim withdrawn in round {turn['round']}: "
                        f"{claim[:90]!r}",
                    )
                )

    # --- accounting adds up -------------------------------------------------------
    if calls:
        if int(final["calls"]) != len(calls):
            out.append(
                Violation(
                    "accounting-is-complete",
                    f"reported {final['calls']} calls, tape records {len(calls)}",
                )
            )
        tape_cost = sum(int(c.get("cost_micros") or 0) for c in calls)
        if int(final["cost_micros"]) != tape_cost:
            out.append(
                Violation(
                    "accounting-is-complete",
                    f"reported {final['cost_micros']} micros, tape sums to {tape_cost}",
                )
            )

    return out


async def _main(run_id: str) -> int:
    from .settings import load_settings
    from .store.mongo import MongoStore

    settings = load_settings()
    if not settings.has_mongo:
        print("MONGODB_URI is not set, so there are no stored runs to validate.")
        return 1
    store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
    events = await store.events_after(run_id, 0)
    await store.close()
    if not events:
        print(f"no events for run {run_id}")
        return 1

    violations = validate(events)
    print(f"{run_id}: {len(events)} events")
    if not violations:
        print("  label is fully supported by the tape")
        return 0
    for violation in violations:
        print(f"  {violation}")
    return 1


if __name__ == "__main__":
    import asyncio

    if len(sys.argv) < 2:
        print("usage: python -m app.label_validator <run_id>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_main(sys.argv[1])))
