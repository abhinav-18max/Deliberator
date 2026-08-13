"""HTTP surface: create a run, stream it, then read the persisted tape back.

The point of these tests is that the live stream and the stored trace are the same events —
a viewer who reloads a finished run sees exactly what a viewer watching it live saw.
"""

import json

from conftest import (
    PANEL,
    comparison_out,
    make_config,
    panel_out,
    stance_out,
    synthesis_out,
)
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.fake import FakeProvider
from app.store.memory import MemoryStore

UNANIMOUS = {
    "panel:m1": [panel_out()],
    "panel:m2": [panel_out()],
    "panel:m3": [panel_out()],
    "comparator": [
        comparison_out(
            "none",
            [stance_out("s1", ["A", "B", "C"])],
            predictions=[{"model_slug": lbl, "stance_id": "s1"} for lbl in "ABC"],
        )
    ],
    "synthesizer": [synthesis_out("Use a token bucket sized to the burst.")],
}


def client(responses: dict | None = None) -> TestClient:
    app = create_app(
        provider=FakeProvider(responses or UNANIMOUS),
        store=MemoryStore(),
        cfg=make_config(),
    )
    return TestClient(app)


def test_health_reports_whether_the_store_is_durable():
    with client() as c:
        body = c.get("/health").json()
    assert body["ok"] is True
    assert body["durable_store"] is False
    assert body["config_fingerprint"]


def test_models_endpoint_serves_the_curated_shortlist():
    with client() as c:
        models = c.get("/models").json()
    assert [m["slug"] for m in models] == PANEL
    assert all(m["family"] for m in models)
    # Capabilities are unverified without a catalogue, and say so rather than claiming support.
    assert all(m["structured_outputs"] is None for m in models)


def test_run_streams_events_and_persists_the_same_tape():
    with client() as c:
        accepted = c.post(
            "/runs", json={"task": "pick a rate limiter", "models": PANEL}
        )
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]

        with c.stream("GET", f"/runs/{run_id}/stream") as stream:
            assert stream.status_code == 200
            streamed = [
                json.loads(line[6:])
                for line in stream.iter_lines()
                if line.startswith("data: ")
            ]

        stored = c.get(f"/runs/{run_id}").json()

    assert streamed[0]["type"] == "run.started"
    assert streamed[-1]["type"] == "run.final"
    assert [e["seq"] for e in streamed] == [e["seq"] for e in stored["events"]]
    assert stored["run"]["status"] == "complete"
    assert stored["run"]["final"]["label"] == "unanimous"
    assert stored["run"]["final"]["final_answer"].startswith("Use a token bucket")


def test_reconnecting_with_last_event_id_resumes_the_tape():
    with client() as c:
        run_id = c.post("/runs", json={"task": "t", "models": PANEL}).json()["run_id"]
        with c.stream("GET", f"/runs/{run_id}/stream") as stream:
            first = [
                json.loads(line[6:])
                for line in stream.iter_lines()
                if line.startswith("data: ")
            ]

        resumed = c.get(
            f"/runs/{run_id}/stream", headers={"Last-Event-ID": str(first[2]["seq"])}
        )

    replayed = [
        json.loads(line[6:])
        for line in resumed.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["seq"] for e in replayed] == [e["seq"] for e in first[3:]]


def test_a_model_outside_the_curated_list_is_refused_with_a_reason():
    with client() as c:
        response = c.post("/runs", json={"task": "t", "models": ["someone/unknown"]})
    assert response.status_code == 422
    assert "curated panel list" in response.json()["detail"]


def test_panel_sharing_a_family_returns_a_correlation_warning():
    responses = dict(UNANIMOUS)
    responses["panel:m1"] = [panel_out()]
    app = create_app(
        provider=FakeProvider(responses),
        store=MemoryStore(),
        cfg=make_config(panel_shortlist=["acme/one", "acme/two"], panel_default=["acme/one"]),
    )
    with TestClient(app) as c:
        warnings = c.post(
            "/runs", json={"task": "t", "models": ["acme/one", "acme/two"]}
        ).json()["warnings"]

    assert any("share the acme family" in w for w in warnings)
