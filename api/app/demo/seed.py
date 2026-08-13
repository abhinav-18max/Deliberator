"""Load the exported demo traces into Mongo.

Idempotent: event `_id`s are deterministic (`<run_id>:<seq>`), so re-seeding is a no-op rather
than a duplicate. Each trace is validated on the way in — a fixture whose label its own tape does
not support would be a bad demo of a product whose whole claim is that labels are checkable.
"""

import asyncio
import json
from pathlib import Path

from ..contracts import TraceEvent
from ..label_validator import validate
from ..settings import load_settings
from ..store.mongo import MongoStore

DEMO_DIR = Path(__file__).resolve().parents[3] / "docs" / "demo"


async def seed() -> int:
    settings = load_settings()
    if not settings.has_mongo:
        print("MONGODB_URI is not set; cannot seed.")
        return 1

    fixtures = sorted(DEMO_DIR.glob("*.json"))
    if not fixtures:
        print(f"no fixtures in {DEMO_DIR}")
        return 1

    store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
    await store.ensure_ready()

    problems = 0
    for path in fixtures:
        payload = json.loads(path.read_text())
        run = payload["run"]
        events = [TraceEvent.model_validate(e) for e in payload["events"]]

        violations = validate(events)
        if violations:
            problems += 1
            print(f"  {path.name}: REJECTED — label not supported by its own tape")
            for violation in violations:
                print(f"      {violation}")
            continue

        run_id = run.pop("_id")
        existing = await store.get_run(run_id)
        if existing is None:
            await store.create_run(run_id, run)
        for event in events:
            await store.append_event(event)
        label = (run.get("final") or {}).get("resolution", "?")
        print(f"  {run_id}  {len(events)} events  {label}")

    await store.close()
    print(f"{len(fixtures) - problems}/{len(fixtures)} trace(s) seeded")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(seed()))
