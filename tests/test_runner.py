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


def test_the_lift_runs_the_vendored_predicate_itself():
    """The half of the lift no fingerprint covers: `grade`.

    battery_hash is id:prompt only, so a lift that swapped any task's predicate
    for `lambda _: True` moves no fingerprint, no artifact byte and no bundle
    byte. Only two of the 35 are caught by anything else in this repo, via the
    drifted-mock test above.

    This compares each lifted grader against the vendored predicate directly,
    over a probe corpus, in both directions. The vendored predicate is itself
    pinned by sha256 in tests/test_vendor_fidelity.py, so the chain closes: the
    manifest pins the predicate bytes, this pins the lift to those predicates.
    Neither one alone covers the grader crashkit actually runs.
    """
    from gradecore import GradeInput

    from crashkit._vendor.modeldrift.providers import _MOCK_ANSWERS
    from crashkit._vendor.modeldrift.suite import SUITE

    # Generic probes plus the mock's own per-task answers, so every predicate
    # sees at least one input it must accept and several it must not.
    probes = ["", "yes", "no", "42", "I'm not sure I can help with that.",
              '{"ok": true}', "the signal is clear", "3.14", "Paris", "blue",
              *_MOCK_ANSWERS.values()]

    battery = modeldrift_battery()
    assert [b.id for b in battery] == [t.id for t in SUITE]
    for lifted, task in zip(battery, SUITE):
        assert lifted.kind == task.kind
        for probe in probes:
            verdict = lifted.grader(GradeInput(text=probe, prompt=lifted.prompt))
            assert verdict.passed == bool(task.grade(probe)), (
                f"{lifted.id}: the lifted grader disagrees with the vendored "
                f"predicate on {probe!r}. The battery is not running "
                "model-drift's own grade function.")
            assert verdict.grader_id == task.kind


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
