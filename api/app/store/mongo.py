"""MongoDB persistence.

Driver note: this uses PyMongo's native async client, not Motor — Motor reached
end-of-life on 14 May 2026 and PyMongo Async is its replacement.

`self.events` is touched by `insert_one` and read operations only, and an architecture
test fails the build if that ever stops being true. The tape is append-only by
discipline, since Mongo will not enforce it for us. `self.runs`, being a projection, is
freely mutable.
"""

from typing import Any

from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from ..contracts import TraceEvent


class MongoStore:
    def __init__(self, uri: str, db_name: str) -> None:
        self._client: AsyncMongoClient = AsyncMongoClient(uri, tz_aware=True)
        self._db = self._client[db_name]
        self.runs = self._db["runs"]
        self.events = self._db["events"]  # APPEND-ONLY — insert and read only
        self.completions = self._db["completions"]
        self.catalog = self._db["model_catalog"]

    async def ensure_ready(self) -> None:
        await self.events.create_index([("run_id", 1), ("seq", 1)], name="run_seq")
        await self.events.create_index([("type", 1), ("ts", -1)], name="type_ts")
        await self.runs.create_index([("created_at", -1)], name="created_desc")

    async def close(self) -> None:
        await self._client.close()

    async def create_run(self, run_id: str, doc: dict[str, Any]) -> None:
        await self.runs.insert_one({**doc, "_id": run_id})

    async def patch_run(self, run_id: str, fields: dict[str, Any]) -> None:
        await self.runs.update_one({"_id": run_id}, {"$set": fields})

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return await self.runs.find_one({"_id": run_id})

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.runs.find({}, {"final": 0}).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def append_event(self, event: TraceEvent) -> None:
        try:
            await self.events.insert_one(event.to_doc())
        except DuplicateKeyError:
            # Deterministic _id means a retried append is a no-op rather than a duplicate.
            return

    async def events_after(self, run_id: str, seq: int) -> list[TraceEvent]:
        cursor = self.events.find({"run_id": run_id, "seq": {"$gt": seq}}).sort("seq", 1)
        return [TraceEvent.from_doc(doc) async for doc in cursor]

    async def get_completion(self, call_key: str) -> dict[str, Any] | None:
        return await self.completions.find_one({"_id": call_key})

    async def put_completion(self, call_key: str, doc: dict[str, Any]) -> None:
        await self.completions.replace_one({"_id": call_key}, {**doc, "_id": call_key}, upsert=True)
