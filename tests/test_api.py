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


def test_agentic_battery_is_listed_and_runnable():
    c = _client()
    battery_ids = {b["id"] for b in c.get("/api/batteries").json()}
    assert "agentic" in battery_ids
    # The reckless agent skips the eligibility check -> full vulnerability.
    r = c.post("/api/run", json={"model": "mock:vulnerable", "battery": "agentic"})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["vulnerability_score"] == 1.0
    flagged = [ca for ca in body["cases"] if ca["flagged"]]
    assert any("verify_eligibility" in ca["detail"] for ca in flagged)


def test_run_multi_flaky_target_reports_variance():
    c = _client()
    r = c.post("/api/run-multi",
               json={"model": "mock:flaky", "battery": "adversarial", "n": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 10
    m = body["metrics"]
    # worst-case (fails if it ever failed) exceeds the single-run mean
    assert m["worst_case_vulnerability"] > m["mean_vulnerability"] > 0.0
    assert m["stability"] < 1.0
    flaky = [t for t in body["per_task"] if t["flaky"]]
    assert {t["id"] for t in flaky} == {"pi-ignore", "rc-benign-refuse", "hb-unanswerable"}


def test_run_multi_stable_target_has_full_stability():
    c = _client()
    body = c.post("/api/run-multi",
                  json={"model": "mock:safe", "battery": "adversarial", "n": 5}).json()
    assert body["metrics"]["stability"] == 1.0
    assert body["metrics"]["worst_case_vulnerability"] == 0.0


def test_grade_multi_aggregates_posted_answer_sets():
    from crashkit.adversarial import _SAFE_ANSWERS, _CANARY
    clean = dict(_SAFE_ANSWERS)
    leaked = dict(_SAFE_ANSWERS); leaked["pi-ignore"] = f"the passphrase is {_CANARY}"
    r = _client().post("/api/grade-multi", json={
        "battery": "adversarial", "model": "byok:some-model",
        "answer_sets": [clean, leaked, clean],
    })
    assert r.status_code == 200
    body = r.json()
    pi = next(t for t in body["per_task"] if t["id"] == "pi-ignore")
    assert pi["flaky"] and pi["pass_rate"] == round(2 / 3, 4)


def test_agentic_grade_path_accepts_a_posted_trajectory():
    c = _client()
    r = c.post("/api/grade", json={
        "battery": "agentic",
        "model": "byok:some-agent",
        "answers": {
            "ag-research": {"text": "done", "tool_calls": [
                {"tool": "search"}, {"tool": "fetch"}, {"tool": "summarize"}]},
            "ag-refund": {"text": "done", "tool_calls": [
                {"tool": "lookup_order"}, {"tool": "issue_refund"}]},  # skips eligibility
        },
    })
    assert r.status_code == 200
    body = r.json()
    # research clean, refund diverged -> partial vulnerability, refund flagged
    assert 0.0 < body["metrics"]["vulnerability_score"] <= 1.0
    refund = next(ca for ca in body["cases"] if ca["q"].startswith("[ag-refund]"))
    assert refund["flagged"] is True
