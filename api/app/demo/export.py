"""Export stored runs to JSON fixtures for the demo pack.

The point is that a reviewer who never gets an API key still sees the real product: the exported
tape is exactly what the pipeline produced, so `make seed && make web` renders genuine
deliberations — verdicts, debate turns, citations and all — with no model calls at all.

Usage:
    uv run python -m app.demo.export <run_id> [<run_id> ...]
    uv run python -m app.demo.export --all
"""

import asyncio
import json
import sys
from pathlib import Path

from ..settings import load_settings
from ..store.mongo import MongoStore

DEMO_DIR = Path(__file__).resolve().parents[3] / "docs" / "demo"


async def export(run_ids: list[str]) -> int:
    settings = load_settings()
    if not settings.has_mongo:
        print("MONGODB_URI is not set; nothing to export.")
        return 1

    store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    if run_ids == ["--all"]:
        run_ids = [
            doc["_id"]
            async for doc in store.runs.find({"status": "complete"}, {"_id": 1})
        ]

    written = 0
    for run_id in run_ids:
        run = await store.get_run(run_id)
        if run is None:
            print(f"  skipped {run_id}: not found")
            continue
        events = await store.events_after(run_id, 0)
        payload = {
            "run": run,
            "events": [event.model_dump(mode="json") for event in events],
        }
        path = DEMO_DIR / f"{run_id}.json"
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        label = (run.get("final") or {}).get("resolution", run.get("status"))
        print(f"  wrote {path.name}  ({len(events)} events, {label})")
        written += 1

    await store.close()
    print(f"{written} run(s) exported to {DEMO_DIR}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(export(sys.argv[1:])))
