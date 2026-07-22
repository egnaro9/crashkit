"""The SQLite run store."""
from crashkit.store import RunStore

EV = {"run": "mock:stable", "git_sha": "abc", "source": "crash_test",
      "metrics": {"faithfulness": 1.0, "reliability": 1.0}, "cases": []}


def test_add_get_roundtrip():
    s = RunStore()
    rid = s.add(EV)
    assert s.get(rid)["run"] == "mock:stable"


def test_leaderboard_puts_worst_accuracy_first():
    s = RunStore()
    s.add({**EV, "run": "good", "metrics": {"faithfulness": 1.0}})
    s.add({**EV, "run": "bad", "metrics": {"faithfulness": 0.3}})
    lb = s.leaderboard()
    assert lb[0]["model"] == "bad" and lb[-1]["model"] == "good"


def test_stores_are_isolated():
    a, b = RunStore(), RunStore()
    a.add(EV)
    assert a.leaderboard() and not b.leaderboard()   # b must not see a's row


def test_get_missing_returns_none():
    assert RunStore().get("nope") is None
