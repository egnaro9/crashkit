"""The never-touches grade path: the server grades answers the browser already
fetched, and never receives a provider key."""
from fastapi.testclient import TestClient

from crashkit import ADVERSARIAL_BATTERY, grade_answers
from crashkit.adversarial import _SAFE_ANSWERS, _VULNERABLE_ANSWERS
from crashkit.app import create_app
from crashkit.store import RunStore


def _client() -> TestClient:
    return TestClient(create_app(RunStore()))


def test_grade_answers_scores_prefetched_text():
    good = grade_answers("openai:gpt-4o", ADVERSARIAL_BATTERY, dict(_SAFE_ANSWERS))
    assert good.vulnerability_score == 0.0 and good.accuracy == 1.0
    bad = grade_answers("openai:gpt-4o", ADVERSARIAL_BATTERY, dict(_VULNERABLE_ANSWERS))
    assert bad.vulnerability_score == 1.0


def test_missing_answer_is_an_error_not_a_silent_fail():
    partial = {t.id: _SAFE_ANSWERS[t.id] for t in ADVERSARIAL_BATTERY[:-1]}   # drop one
    r = grade_answers("m", ADVERSARIAL_BATTERY, partial)
    errs = [res for res in r.results if res.verdict.grader_id == "error"]
    assert len(errs) == 1 and r.reliability < 1.0


def test_battery_endpoint_returns_the_prompts():
    r = _client().get("/api/battery/adversarial").json()
    assert r["battery"] == "adversarial"
    assert len(r["tasks"]) == len(ADVERSARIAL_BATTERY)
    assert {"id", "prompt", "kind"} <= set(r["tasks"][0])


def test_grade_endpoint_stores_and_scores():
    c = _client()
    body = {"battery": "adversarial", "model": "openai:gpt-4o", "answers": dict(_VULNERABLE_ANSWERS)}
    r = c.post("/api/grade", json=body).json()
    assert r["metrics"]["vulnerability_score"] == 1.0 and "id" in r
    assert any(row["id"] == r["id"] for row in c.get("/api/runs").json())


def test_grade_endpoint_has_no_key_field_so_a_stray_key_is_ignored():
    c = _client()
    body = {"battery": "adversarial", "model": "m", "answers": dict(_SAFE_ANSWERS),
            "key": "sk-SECRET-must-not-persist"}
    r = c.post("/api/grade", json=body)
    assert r.status_code == 200
    stored = c.get(f"/api/runs/{r.json()['id']}").json()
    assert "sk-SECRET" not in str(stored)          # the key never entered the system
