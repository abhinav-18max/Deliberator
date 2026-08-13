"""The orchestrator: plain code that owns the flow.

Models never talk to each other. Every message passes through here, and every decision about
who is called, what they see, and when to stop is made in code. That separation — control in
code, judgement in models — is the single most important property of the design, so this file
contains no prompts and makes no judgement calls of its own.

It is an async generator of trace events, which is what lets one code path serve three
consumers: the SSE stream, the persisted tape, and the replay used by the demo and the eval
harness. Nothing can drift between the live view and the record.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from . import ladder
from .calls import Caller
from .cluster import reduce_round
from .contracts import (
    DebateTurn,
    Dispute,
    DisputeOutcome,
    DisputeType,
    Dropout,
    Envelope,
    EventType,
    FinalAnswer,
    Mechanism,
    Mode,
    PanelAnswer,
    Role,
    RoleAssignment,
    Stage,
    TraceEvent,
    Verdict,
    Verification,
    VerifyOutcome,
)
from .contracts.request import DeliberateRequest
from .providers.base import Completion, LLMPort
from .roles import CapabilityIndex, ConfigError, ResolvedRole, RoleRegistry, validate_panel
from .settings import Config
from .stages import compare, debate, fanout, guard, normalize, redteam, synthesize, verify


async def merge_streams(streams: list[AsyncIterator[Any]]) -> AsyncIterator[Any]:
    """Fan several async generators into one, preserving arrival order.

    Disputes are independent axes, so their debates run as concurrent state machines. Wall
    clock is then the slowest single dispute rather than the sum of all of them, and turns
    still stream to the interface as they land.
    """
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    async def pump(stream: AsyncIterator[Any]) -> None:
        try:
            async for item in stream:
                await queue.put(item)
        finally:
            await queue.put(sentinel)

    tasks = [asyncio.create_task(pump(s)) for s in streams]
    finished = 0
    try:
        while finished < len(tasks):
            item = await queue.get()
            if item is sentinel:
                finished += 1
                continue
            yield item
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)


class Orchestrator:
    def __init__(
        self,
        provider: LLMPort,
        cfg: Config,
        *,
        capabilities: CapabilityIndex | None = None,
    ) -> None:
        self.provider = provider
        self.cfg = cfg
        self.registry = RoleRegistry(cfg, capabilities)
        self.capabilities = capabilities

    async def run(self, run_id: str, request: DeliberateRequest) -> AsyncIterator[TraceEvent]:
        started = time.monotonic()
        self._seq = 0
        self._calls: list[Completion] = []
        caller = Caller(self.provider, on_call=self._calls.append)
        caps = self.cfg.caps

        roles = self.registry.resolve_all(
            panel=request.models,
            overrides={o.role: o.slug for o in request.overrides},
        )
        gate_validated = self.registry.gate_validated(roles[Role.COMPARATOR])
        panel_check = validate_panel(self.cfg, request.models)

        yield self._event(
            run_id,
            EventType.RUN_STARTED,
            {
                "task": request.task,
                "has_context": bool(request.context),
                "models": request.models,
                "mode": request.mode.value,
                "floor_model": request.floor_model(),
                "roles": [self._role_payload(r) for r in roles.values()],
                "gate_validated": gate_validated,
                "warnings": panel_check.warnings
                + [n for r in roles.values() for n in r.notes],
                "config_fingerprint": self.cfg.fingerprint(),
            },
        )

        # ---- Stage 0: guard -------------------------------------------------------
        yield self._event(run_id, EventType.STAGE_ENTERED, {"stage": Stage.GUARD.value})
        envelope = guard.build_envelope(request)
        guard.check_context_fit(envelope, request.models, self.capabilities)

        # ---- Stage 1: fan-out ----------------------------------------------------
        yield self._event(run_id, EventType.STAGE_ENTERED, {"stage": Stage.FANOUT.value})
        answers: list[PanelAnswer] = []
        dropouts: list[Dropout] = []
        async for item in fanout.run(
            caller, envelope, request.models, timeout_s=caps.panel_call_timeout_s
        ):
            if isinstance(item, Dropout):
                dropouts.append(item)
                yield self._event(run_id, EventType.PANEL_DROPOUT, item.model_dump(mode="json"))
                continue
            if not item.key_claims and roles[Role.NORMALIZER].enabled:
                item = await normalize.recover(caller, roles[Role.NORMALIZER], item)
                if item.normalized:
                    yield self._event(
                        run_id, EventType.NORMALIZE_APPLIED, {"model": item.model}
                    )
            answers.append(item)
            yield self._event(run_id, EventType.PANEL_ANSWER, item.model_dump(mode="json"))
        for event in self._drain(run_id):
            yield event

        if not answers:
            yield self._event(
                run_id,
                EventType.RUN_ERROR,
                {"detail": "no model produced an answer", "dropouts": len(dropouts)},
            )
            return

        if len(answers) < caps.min_quorum:
            # Below quorum there is nothing to compare. Degrade to single-answer mode and say
            # so, rather than pretending a panel of one deliberated.
            result = ladder.gate_failure(
                answers[0].model, f"only {len(answers)} model(s) answered, below quorum"
            )
            async for event in self._finalize(
                run_id,
                caller,
                roles,
                envelope,
                result,
                stances=[],
                answers=answers,
                disputes=[],
                verifications=[],
                turns=[],
                request=request,
                gate_validated=gate_validated,
                started=started,
            ):
                yield event
            return

        # ---- Stage 2: compare (the gate) ----------------------------------------
        yield self._event(run_id, EventType.STAGE_ENTERED, {"stage": Stage.COMPARE.value})
        order = compare.presentation_order(run_id, len(answers))
        comparison = await compare.run(
            caller,
            roles[Role.COMPARATOR],
            envelope,
            answers,
            order=order,
            timeout_s=caps.per_call_timeout_s,
        )
        if comparison is not None and request.mode is Mode.RIGOROUS:
            second = await compare.run(
                caller,
                roles[Role.COMPARATOR],
                envelope,
                answers,
                order=list(reversed(order)),
                timeout_s=caps.per_call_timeout_s,
            )
            comparison = compare.merge_reversed(comparison, second)
        for event in self._drain(run_id):
            yield event

        if comparison is None:
            result = ladder.gate_failure(
                request.floor_model(), "the comparator returned no usable verdict"
            )
            async for event in self._finalize(
                run_id, caller, roles, envelope, result,
                stances=[], answers=answers, disputes=[], verifications=[], turns=[],
                request=request, gate_validated=gate_validated, started=started,
            ):
                yield event
            return

        yield self._event(
            run_id,
            EventType.COMPARE_VERDICT,
            {
                "verdict": comparison.verdict.value,
                "justification": comparison.justification,
                "unstable": comparison.unstable,
                "stances": [s.model_dump(mode="json") for s in comparison.stances],
                "dispute_count": len(comparison.disputes),
            },
        )

        # ---- Rigorous mode: attack a unanimous panel ----------------------------
        red_team_attack: str | None = None
        if request.mode is Mode.RIGOROUS and comparison.verdict is not Verdict.MATERIAL:
            consensus = comparison.stances[0] if comparison.stances else None
            if consensus:
                advocate = next(
                    (a for a in answers if a.model == consensus.strongest), answers[0]
                )
                out, _cost = await redteam.run(
                    caller,
                    roles[Role.RED_TEAM],
                    envelope,
                    consensus,
                    advocate.answer,
                    timeout_s=caps.per_call_timeout_s,
                )
                if out is not None:
                    red_team_attack = out.attack
                for event in self._drain(run_id):
                    yield event

        # ---- Stage 3: resolve ---------------------------------------------------
        verifications: list[Verification] = []
        outcomes: list[DisputeOutcome] = []
        turns: list[DebateTurn] = []
        stances = comparison.stances

        if comparison.verdict is Verdict.MATERIAL:
            yield self._event(run_id, EventType.STAGE_ENTERED, {"stage": Stage.RESOLVE.value})
            for dispute in comparison.disputes:
                yield self._event(
                    run_id, EventType.DISPUTE_OPENED, dispute.model_dump(mode="json")
                )

            to_debate: list[Dispute] = []
            checkable = [d for d in comparison.disputes if d.type is DisputeType.FACTUAL]
            verified_now, dropped = (
                checkable[: caps.max_verified_disputes],
                checkable[caps.max_verified_disputes :],
            )
            for dispute in dropped:
                # A silent cap reads as "we checked everything", so the drop is recorded.
                outcome = DisputeOutcome(
                    dispute_id=dispute.id,
                    mechanism=Mechanism.UNRESOLVED,
                    resolved=False,
                    note=f"not checked: over the cap of {caps.max_verified_disputes}"
                    " grounded checks per run",
                )
                outcomes.append(outcome)
                yield self._event(
                    run_id, EventType.DISPUTE_CLOSED, outcome.model_dump(mode="json")
                )

            if verified_now:
                results = await asyncio.gather(
                    *(
                        verify.run(
                            caller,
                            roles[Role.VERIFIER],
                            dispute,
                            timeout_s=caps.per_call_timeout_s,
                        )
                        for dispute in verified_now
                    )
                )
                for dispute, verification in zip(verified_now, results, strict=True):
                    verifications.append(verification)
                    yield self._event(
                        run_id, EventType.VERIFY_RESULT, verification.model_dump(mode="json")
                    )
                    if verification.outcome is VerifyOutcome.UNVERIFIABLE:
                        # No external arbiter exists after all, so this becomes a judgement
                        # call rather than a fact — and is debated instead of stamped.
                        to_debate.append(dispute)
                        continue
                    outcome = (
                        DisputeOutcome(
                            dispute_id=dispute.id,
                            mechanism=Mechanism.VERIFICATION,
                            resolved=True,
                            winning_stance=verification.winning_stance,
                            note="evidence beats rhetoric",
                        )
                        if verification.resolves
                        else DisputeOutcome(
                            dispute_id=dispute.id,
                            mechanism=Mechanism.UNRESOLVED,
                            resolved=False,
                            note="sources conflict or the record is insufficient",
                        )
                    )
                    outcomes.append(outcome)
                    yield self._event(
                        run_id, EventType.DISPUTE_CLOSED, outcome.model_dump(mode="json")
                    )
                for event in self._drain(run_id):
                    yield event

            for dispute in comparison.disputes:
                if dispute.type is DisputeType.INTERPRETATION:
                    # No legitimate winner exists; branching is the honest resolution.
                    outcome = DisputeOutcome(
                        dispute_id=dispute.id,
                        mechanism=Mechanism.BRANCH,
                        resolved=False,
                        note="two valid readings; surfaced as a conditional",
                    )
                    outcomes.append(outcome)
                    yield self._event(
                        run_id, EventType.DISPUTE_CLOSED, outcome.model_dump(mode="json")
                    )
                elif dispute.type is DisputeType.APPROACH:
                    to_debate.append(dispute)

            if to_debate:
                round0_claims = {a.model: a.key_claims for a in answers}
                streams = [
                    debate.run(
                        caller,
                        envelope,
                        dispute,
                        stances,
                        round0_claims,
                        max_rounds=caps.max_rounds,
                        timeout_s=caps.per_call_timeout_s,
                    )
                    for dispute in to_debate
                ]
                async for item in merge_streams(streams):
                    if isinstance(item, DebateTurn):
                        turns.append(item)
                        yield self._event(
                            run_id, EventType.DEBATE_TURN, item.model_dump(mode="json")
                        )
                    else:
                        outcomes.append(item)
                        yield self._event(
                            run_id, EventType.DISPUTE_CLOSED, item.model_dump(mode="json")
                        )
                for event in self._drain(run_id):
                    yield event

                # One re-cluster over every turn, so votes reflect concessions from all axes
                # before anything is counted.
                folded = reduce_round(stances, turns)
                if folded.concessions or folded.merges:
                    stances = folded.stances
                    yield self._event(
                        run_id,
                        EventType.CLUSTER_CONVERGED,
                        {
                            "concessions": folded.concessions,
                            "merges": folded.merges,
                            "surviving": folded.surviving_ids,
                        },
                    )

        # ---- Stage 4: finalize --------------------------------------------------
        result = ladder.choose(
            ladder.LadderInput(
                verdict=comparison.verdict,
                stances=stances,
                disputes=comparison.disputes,
                outcomes=outcomes,
                verifications=verifications,
                predictions=comparison.predictions,
                answers=answers,
                turns=turns,
                floor_model=request.floor_model(),
                dropouts=dropouts,
                gate_validated=gate_validated,
                red_team_attack=red_team_attack,
            )
        )
        async for event in self._finalize(
            run_id,
            caller,
            roles,
            envelope,
            result,
            stances=stances,
            answers=answers,
            disputes=comparison.disputes,
            verifications=verifications,
            turns=turns,
            request=request,
            gate_validated=gate_validated,
            started=started,
        ):
            yield event

    # -- internals -----------------------------------------------------------------

    async def _finalize(
        self,
        run_id: str,
        caller: Caller,
        roles: dict[Role, ResolvedRole],
        envelope: Envelope,
        result: ladder.LadderResult,
        *,
        stances: list,
        answers: list[PanelAnswer],
        disputes: list[Dispute],
        verifications: list[Verification],
        turns: list[DebateTurn],
        request: DeliberateRequest,
        gate_validated: bool,
        started: float,
    ) -> AsyncIterator[TraceEvent]:
        yield self._event(run_id, EventType.STAGE_ENTERED, {"stage": Stage.FINALIZE.value})
        yield self._event(
            run_id,
            EventType.LADDER_RUNG,
            {
                "rung": int(result.rung),
                "label": result.label.value,
                "resolution": result.resolution,
                "confidence": result.confidence.value,
                "winning_stance": result.winning_stance,
                "tie_break_reason": result.tie_break_reason,
                "unresolved": result.unresolved,
                "branches": result.branches,
            },
        )

        answer_text, caveats, _cost = await synthesize.run(
            caller,
            roles[Role.SYNTHESIZER],
            envelope,
            result,
            stances=stances,
            answers=answers,
            disputes=disputes,
            verifications=verifications,
            turns=turns,
            timeout_s=self.cfg.caps.per_call_timeout_s,
        )
        for event in self._drain(run_id):
            yield event

        final = FinalAnswer(
            final_answer=answer_text,
            label=result.label,
            resolution=result.resolution,
            confidence=result.confidence,
            caveats=[*result.caveats, *caveats],
            rung=result.rung,
            tie_break_reason=result.tie_break_reason,
            unresolved_disputes=result.unresolved,
            dissent=result.dissent,
            panel=[a.model for a in answers],
            referees=[
                RoleAssignment(
                    role=r.role.value,
                    slug=r.slug,
                    prompt_version=r.prompt_version,
                    off_panel=not r.on_panel,
                )
                for r in roles.values()
            ],
            gate_validated=gate_validated,
            calls=len(self._calls),
            cost_micros=sum(c.usage.cost_micros for c in self._calls),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        yield self._event(run_id, EventType.RUN_FINAL, final.model_dump(mode="json"))

    def _event(self, run_id: str, type_: EventType, payload: dict[str, Any]) -> TraceEvent:
        self._seq += 1
        return TraceEvent(run_id=run_id, seq=self._seq, type=type_, payload=payload)

    def _drain(self, run_id: str) -> list[TraceEvent]:
        """Emit accounting for calls made since the last drain: role, slug, which upstream
        provider actually served it, tokens and cost. Per-stage cost in the trace is what makes
        the fast/rigorous trade visible in the product instead of argued in a README."""
        events = []
        for completion in self._calls[getattr(self, "_drained", 0) :]:
            events.append(
                self._event(
                    run_id,
                    EventType.MODEL_CALL,
                    {
                        "role": completion.role,
                        "slug": completion.slug,
                        "upstream_provider": completion.upstream_provider,
                        "routing_unpinned": completion.routing_unpinned,
                        "generation_id": completion.generation_id,
                        "call_key": completion.call_key,
                        "prompt_tokens": completion.usage.prompt_tokens,
                        "completion_tokens": completion.usage.completion_tokens,
                        "cost_micros": completion.usage.cost_micros,
                        "latency_ms": completion.latency_ms,
                    },
                )
            )
        self._drained = len(self._calls)
        return events

    @staticmethod
    def _role_payload(role: ResolvedRole) -> dict[str, Any]:
        return {
            "role": role.role.value,
            "slug": role.slug,
            "prompt_version": role.prompt_version,
            "enabled": role.enabled,
            "on_panel": role.on_panel,
            "notes": list(role.notes),
        }


__all__ = ["ConfigError", "Orchestrator", "merge_streams"]
