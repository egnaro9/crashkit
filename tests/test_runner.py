"""The Phase 0 run: model-drift's SUITE, mock transport, graded through gradecore,
serialized to the eval_run wire shape — all deterministic and offline."""
from crashkit._vendor.modeldrift.providers import Model

from crashkit import battery_hash, modeldrift_battery, run, to_eval_run

STABLE = Model("mock:stable", "Mock", "mock", "mock", "NONE")
DRIFTED = Model("mock:drifted", "Mock (drifted)", "mock", "mock-drifted", "NONE")


def test_stable_mock_scores_perfectly_and_deterministically():
    r1, r2 = run(STABLE), run(STABLE)
    assert r1.accuracy == 1.0
    assert r1.accuracy == r2.accuracy                 # deterministic
    assert r1.reliability == 1.0                      # no errors, no truncations
    assert all(res.verdict.passed for res in r1.results)   # gradecore Verdicts


def test_drifted_mock_is_caught_by_gradecore():
    r = run(DRIFTED)
    assert r.accuracy < 1.0
    assert len([res for res in r.results if not res.verdict.passed]) == 2


def test_the_lift_preserves_every_task_id_and_prompt():
    # NOT a provenance check, and it never was one: both sides read the same
    # SUITE, so an edited suite moves both hashes together and this stays
    # green. That job belongs to tests/test_vendor_fidelity.py.
    #
    # What it does prove is that two independent implementations agree over
    # that SUITE: crashkit's Task -> BatteryTask lift through
    # gradecore.suite_hash, against model-drift's own suite_hash. A lift that
    # dropped, reordered or rewrote an id or prompt shows up here.
    #
    # Scope, precisely: battery.py lifts four fields (id, prompt, kind, grade)
    # and this hash covers two of them. A lift that mangled `kind` or wrapped
    # the wrong `grade` passes this. Nothing here reaches the answer keys.
    from crashkit._vendor.modeldrift.suite import suite_hash as md_hash
    assert battery_hash(modeldrift_battery()) == md_hash()


def test_serialization_is_eval_history_shaped():
    ev = to_eval_run(run(STABLE))
    assert set(ev) >= {"run", "git_sha", "label", "source", "metrics", "cases"}
    assert ev["source"] == "crash_test"
    assert ev["metrics"]["faithfulness"] == 1.0
    assert len(ev["cases"]) == int(ev["metrics"]["n_cases"])
    assert set(ev["cases"][0]) >= {"q", "answer", "scores", "flagged", "note"}


def test_serialized_run_is_fully_deterministic():
    # The whole point — no LLM judge, no timestamps, no latency in the wire form.
    assert to_eval_run(run(STABLE)) == to_eval_run(run(STABLE))
