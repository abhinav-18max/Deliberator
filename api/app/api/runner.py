"""Drives an orchestrator run into the tape and the live stream.

Everything downstream of the orchestrator reads the same event objects: the store appends
them, the broadcast pushes them to connected viewers, and the `runs` projection is updated
from them. The projection is derived, never authored — if this process dies mid-run, the tape
is still complete enough to rebuild it.
"""

import asyncio
from datetime import UTC, datetime

from ..contracts import EventType, RunStatus, TraceEvent
from ..contracts.request import DeliberateRequest
from ..orchestrator import Orchestrator
from ..store.base import StorePort
from ..store.broadcast import Broadcast


async def execute(
    *,
    run_id: str,
    request: DeliberateRequest,
    orchestrator: Orchestrator,
    store: StorePort,
    broadcast: Broadcast,
) -> None:
    last_seq = 0
    status = RunStatus.FAILED
    try:
        async for event in orchestrator.run(run_id, request):
            last_seq = event.seq
            await store.append_event(event)
            broadcast.publish(run_id, event)
            await _project(store, event)
            if event.type is EventType.RUN_FINAL:
                status = RunStatus.COMPLETE
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — the failure belongs in the tape, not the log only
        error = TraceEvent(
            run_id=run_id,
            seq=last_seq + 1,
            type=EventType.RUN_ERROR,
            payload={"detail": str(exc), "kind": type(exc).__name__},
        )
        await store.append_event(error)
        broadcast.publish(run_id, error)
    finally:
        await store.patch_run(
            run_id,
            {"status": status.value, "updated_at": datetime.now(UTC).isoformat()},
        )
        broadcast.publish(run_id, None)


async def _project(store: StorePort, event: TraceEvent) -> None:
    fields: dict = {"updated_at": datetime.now(UTC).isoformat()}
    if event.type is EventType.STAGE_ENTERED:
        fields["stage"] = event.payload.get("stage")
    elif event.type is EventType.RUN_FINAL:
        fields["final"] = event.payload
        fields["cost_micros"] = event.payload.get("cost_micros", 0)
        fields["calls"] = event.payload.get("calls", 0)
        fields["label"] = event.payload.get("label")
        fields["confidence"] = event.payload.get("confidence")
    elif event.type is EventType.RUN_STARTED:
        fields["warnings"] = event.payload.get("warnings", [])
        fields["roles"] = event.payload.get("roles", [])
    else:
        return
    await store.patch_run(event.run_id, fields)
