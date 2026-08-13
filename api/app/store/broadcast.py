"""In-process fan-out of trace events to SSE subscribers.

A viewer that joins late reads the tape from `seq > Last-Event-ID` and then subscribes
here, so a reload mid-run rebuilds the timeline identically. Atlas would give us change
streams for free; v1 does not need them, and swapping this module for a change-stream tail
is the only change required to run the API with multiple workers.
"""

import asyncio
from collections.abc import AsyncIterator

from ..contracts import TraceEvent

_QUEUE_MAX = 512


class Broadcast:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[TraceEvent | None]]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue[TraceEvent | None]:
        queue: asyncio.Queue[TraceEvent | None] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._subs.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[TraceEvent | None]) -> None:
        subs = self._subs.get(run_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._subs.pop(run_id, None)

    def publish(self, run_id: str, event: TraceEvent | None) -> None:
        """None closes the stream. Never blocks the pipeline: a subscriber that cannot
        keep up is dropped, and it will recover the missed events from the tape on
        reconnect."""
        for queue in list(self._subs.get(run_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.unsubscribe(run_id, queue)

    async def stream(self, run_id: str) -> AsyncIterator[TraceEvent]:
        queue = self.subscribe(run_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            self.unsubscribe(run_id, queue)


broadcast = Broadcast()
