"""Deliberate, operator-invoked deletion. The only place in the codebase allowed to remove events.

`store/mongo.py` touches the tape with `insert_one` and reads, and an architecture test enforces
that. Housekeeping still has to be possible, so it lives here instead of being smuggled into the
store: one file, one entry point, dry-run by default. Anything that deletes history should be easy
to find and hard to trigger by accident.

Two jobs:

*   **De-duplicate runs.** Re-running the same task while developing leaves near-identical runs that
    clutter the history and make the demo pack ambiguous. One survivor per (task, mode, panel), and
    the tapes exported to `docs/demo/` are always the survivors — they are cited by name in the
    documentation, so their ids may not change.
*   **Sweep orphans.** Events whose run document is gone are unreachable by every reader, so they
    are cost without meaning.

    uv run python -m app.store.maintenance            # report only
    uv run python -m app.store.maintenance --apply    # delete
"""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..settings import load_settings
from .mongo import MongoStore

DEMO_DIR = Path(__file__).resolve().parents[3] / "docs" / "demo"


def protected_ids() -> set[str]:
    """Runs cited by the documentation. Deleting one would leave demo.md pointing at nothing."""
    return {path.stem for path in DEMO_DIR.glob("*.json")}


def _group_key(run: dict[str, Any]) -> tuple[str, str, str]:
    request = run.get("request") or {}
    return (
        (request.get("task") or "").strip(),
        request.get("mode") or "",
        ",".join(request.get("models") or []),
    )


def _rank(run: dict[str, Any], protected: set[str]) -> tuple[int, int, str]:
    """Higher sorts first: protected, then complete, then most recent."""
    return (
        1 if run["_id"] in protected else 0,
        1 if run.get("final") else 0,
        run.get("created_at") or "",
    )


async def dedupe(*, apply: bool = False) -> int:
    settings = load_settings()
    if not settings.has_mongo:
        print("MONGODB_URI is not set; nothing to do.")
        return 1

    store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
    protected = protected_ids()
    runs = [doc async for doc in store.runs.find({})]

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        groups[_group_key(run)].append(run)

    doomed: list[dict[str, Any]] = []
    print(f"{len(runs)} run(s), {len(groups)} distinct task(s). Protected: {len(protected)}.\n")
    for key, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(members) < 2:
            continue
        ranked = sorted(members, key=lambda r: _rank(r, protected), reverse=True)
        keeper, losers = ranked[0], ranked[1:]
        doomed.extend(losers)
        flag = " (cited by docs/demo)" if keeper["_id"] in protected else ""
        print(f"[{key[1]}] {key[0][:60]}…")
        print(f"    keep   {keeper['_id']}  {keeper.get('created_at', '')[:19]}{flag}")
        for loser in losers:
            events = await store.events.count_documents({"run_id": loser["_id"]})
            print(
                f"    drop   {loser['_id']}  {loser.get('created_at', '')[:19]}"
                f"  ({events} events)"
            )

    known_ids = {run["_id"] for run in runs}
    # distinct() returns the whole list, not a cursor.
    orphan_ids = {
        run_id
        for run_id in await store.events.distinct("run_id")
        if run_id not in known_ids
    }
    if orphan_ids:
        print(f"\n{len(orphan_ids)} run(s) have events but no run document: {sorted(orphan_ids)}")

    if not doomed and not orphan_ids:
        print("\nNothing to remove.")
        await store.close()
        return 0

    if not apply:
        print(
            f"\nDry run. Would remove {len(doomed)} duplicate run(s)"
            f"{f' and {len(orphan_ids)} orphan tape(s)' if orphan_ids else ''}."
            "\nRe-run with --apply to delete."
        )
        await store.close()
        return 0

    removed_events = 0
    for run in doomed:
        result = await store.events.delete_many({"run_id": run["_id"]})
        removed_events += result.deleted_count
        await store.runs.delete_one({"_id": run["_id"]})
    for run_id in orphan_ids:
        result = await store.events.delete_many({"run_id": run_id})
        removed_events += result.deleted_count

    remaining = await store.runs.count_documents({})
    print(
        f"\nRemoved {len(doomed)} run(s) and {removed_events} event(s). "
        f"{remaining} run(s) remain."
    )

    # Completions are keyed by call key and shared across runs, so they are never touched here:
    # they are the recorded fixtures that make `make eval` free and `make demo` key-less.
    kept = await store.completions.count_documents({})
    print(f"{kept} recorded completion(s) left intact — they are replay fixtures, not run data.")
    await store.close()
    return 0


async def report_integrity() -> None:
    """Confirm the tape has no duplicate (run_id, seq) pairs, which the deterministic `_id`
    should make impossible. Cheap to verify, and the answer belongs in the open."""
    settings = load_settings()
    store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
    pipeline = [
        {"$group": {"_id": {"run": "$run_id", "seq": "$seq"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "duplicates"},
    ]
    found = [doc async for doc in await store.events.aggregate(pipeline)]
    print(f"duplicate (run_id, seq) pairs: {found[0]['duplicates'] if found else 0}")
    await store.close()


if __name__ == "__main__":
    if "--integrity" in sys.argv:
        raise SystemExit(asyncio.run(report_integrity()))
    raise SystemExit(asyncio.run(dedupe(apply="--apply" in sys.argv)))
