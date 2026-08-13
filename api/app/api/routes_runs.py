"""Run endpoints.

`POST /runs` returns immediately and the client opens `GET /runs/{id}/stream`, rather than
streaming from the POST itself. That buys two things worth having: run URLs are shareable and
reloadable, and a reconnect resumes from `Last-Event-ID` by replaying the tape — so a viewer
who joins late or refreshes mid-run rebuilds the identical timeline.
"""

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ulid import ULID

from ..contracts import RunStatus, TraceEvent
from ..contracts.request import DeliberateRequest
from ..roles import ConfigError, validate_panel
from . import runner

router = APIRouter(tags=["runs"])


class RunAccepted(BaseModel):
    run_id: str
    warnings: list[str] = []


@router.post("/runs", response_model=RunAccepted, status_code=202)
async def create_run(request: Request, body: DeliberateRequest) -> RunAccepted:
    state = request.app.state
    try:
        check = validate_panel(state.config, body.models)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run_id = str(ULID())
    await state.store.create_run(
        run_id,
        {
            "request": body.model_dump(mode="json"),
            "status": RunStatus.RUNNING.value,
            "stage": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "config_fingerprint": state.config.fingerprint(),
        },
    )

    task = asyncio.create_task(
        runner.execute(
            run_id=run_id,
            request=body,
            orchestrator=state.build_orchestrator(),
            store=state.store,
            broadcast=state.broadcast,
        )
    )
    # Hold a reference so the task is not garbage collected mid-flight.
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)

    return RunAccepted(run_id=run_id, warnings=check.warnings)


@router.get("/runs")
async def list_runs(request: Request, limit: int = 50) -> list[dict]:
    return await request.app.state.store.list_runs(limit)


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str) -> dict:
    store = request.app.state.store
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    events = await store.events_after(run_id, 0)
    return {"run": run, "events": [e.model_dump(mode="json") for e in events]}


def _sse(event: TraceEvent) -> str:
    """Frames are deliberately *unnamed*.

    Setting an `event:` field makes the browser dispatch that name instead of `message`, so
    `EventSource.onmessage` never fires and a client has to register a listener per event type —
    meaning any new event type is silently dropped. The type travels inside the payload, which
    every consumer parses anyway. The comment line keeps `curl` output readable.
    """
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f": {event.type.value}\nid: {event.seq}\ndata: {payload}\n\n"


@router.get("/runs/{run_id}/stream")
async def stream_run(request: Request, run_id: str) -> Response:
    state = request.app.state
    run = await state.store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")

    last_id = request.headers.get("last-event-id")
    resume_from = int(last_id) if (last_id or "").isdigit() else 0

    async def body():
        # Subscribe before reading the tape, so an event landing between the two is queued
        # rather than lost.
        queue = state.broadcast.subscribe(run_id)
        try:
            seen = resume_from
            for event in await state.store.events_after(run_id, resume_from):
                seen = event.seq
                yield _sse(event)
            if (await state.store.get_run(run_id) or {}).get("status") != RunStatus.RUNNING.value:
                return
            while True:
                event = await queue.get()
                if event is None:
                    return
                if event.seq <= seen:
                    continue  # already replayed from the tape
                yield _sse(event)
        finally:
            state.broadcast.unsubscribe(run_id, queue)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
