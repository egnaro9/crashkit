"""The playground + leaderboard API."""
from fastapi.testclient import TestClient

from crashkit.app import create_app
from crashkit.store import RunStore


def _client() -> TestClient:
    return TestClient(create_app(RunStore()))


def test_models_lists_the_mocks():
    ids = {m["id"] for m in _client().get("/api/models").json()}
    assert {"mock:stable", "mock:drifted"} <= ids


def test_run_grades_stores_and_appears_on_the_leaderboard():
    c = _client()
    r = c.post("/api/run", json={"model": "mock:stable"})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["faithfulness"] == 1.0 and "id" in body
    assert any(row["id"] == body["id"] for row in c.get("/api/runs").json())


def test_drifted_run_is_caught_and_readable_per_case():
    c = _client()
    rid = c.post("/api/run", json={"model": "mock:drifted"}).json()["id"]
    one = c.get(f"/api/runs/{rid}").json()
    assert one["metrics"]["faithfulness"] < 1.0
    assert any(case["flagged"] for case in one["cases"])   # the failures show


def test_unknown_model_is_404():
    assert _client().post("/api/run", json={"model": "gpt-nope"}).status_code == 404
