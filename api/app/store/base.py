"""The persistence port.

Two collections with two different jobs, and the distinction is load-bearing:

*   `events` is an immutable tape — insert only, ever. It is the source of truth.
*   `runs` is a mutable projection of that tape for the list view and the API. It may be
    `$set` freely, and it can be rebuilt by replaying events if a process dies mid-run.

`completions` is neither: it is the recorded-fixture store keyed by call key, with no TTL,
because those documents are test fixtures rather than a cache.
"""

from typing import Any, Protocol

from ..contracts import TraceEvent


class StorePort(Protocol):
    # Whether a run survives a restart. Reported by /health, so the answer comes from the
    # store actually in use rather than from configuration that may not have been applied.
    durable: bool

    async def ensure_ready(self) -> None: ...

    async def create_run(self, run_id: str, doc: dict[str, Any]) -> None: ...

    async def patch_run(self, run_id: str, fields: dict[str, Any]) -> None: ...

    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]: ...

    async def append_event(self, event: TraceEvent) -> None: ...

    async def events_after(self, run_id: str, seq: int) -> list[TraceEvent]: ...

    async def get_completion(self, call_key: str) -> dict[str, Any] | None: ...

    async def put_completion(self, call_key: str, doc: dict[str, Any]) -> None: ...
