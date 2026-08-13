"""In-process store. Used by the whole test suite, so tests need no network."""

from typing import Any

from ..contracts import TraceEvent


class MemoryStore:
    durable = False

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[int, TraceEvent]] = {}
        self.completions: dict[str, dict[str, Any]] = {}

    async def ensure_ready(self) -> None:
        return None

    async def create_run(self, run_id: str, doc: dict[str, Any]) -> None:
        self.runs[run_id] = {**doc, "_id": run_id}
        self.events.setdefault(run_id, {})

    async def patch_run(self, run_id: str, fields: dict[str, Any]) -> None:
        self.runs.setdefault(run_id, {"_id": run_id}).update(fields)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.get(run_id)

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        ordered = sorted(
            self.runs.values(), key=lambda r: r.get("created_at", ""), reverse=True
        )
        return ordered[:limit]

    async def append_event(self, event: TraceEvent) -> None:
        # Insert-only, matching the Mongo tape: a duplicate seq is a bug, not an update.
        bucket = self.events.setdefault(event.run_id, {})
        if event.seq in bucket:
            return
        bucket[event.seq] = event

    async def events_after(self, run_id: str, seq: int) -> list[TraceEvent]:
        bucket = self.events.get(run_id, {})
        return [bucket[s] for s in sorted(bucket) if s > seq]

    async def get_completion(self, call_key: str) -> dict[str, Any] | None:
        return self.completions.get(call_key)

    async def put_completion(self, call_key: str, doc: dict[str, Any]) -> None:
        self.completions[call_key] = doc
