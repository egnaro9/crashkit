"""Run-N-times variance: a deterministic target is perfectly stable, a flaky one
exposes the intermittent leak, and the report separates mean from worst-case."""
from modeldrift.providers import Model

from crashkit import (
    ADVERSARIAL_BATTERY,
    aggregate_runs,
    flaky_transport,
    grade_answer_sets,
    mock_transport,
    run,
    run_n,
    to_variance_report,
)

SAFE = Model("mock:safe", "Safe", "mock", "safe", "NONE")
VULN = Model("mock:vulnerable", "Vulnerable", "mock", "vulnerable", "NONE")
FLAKY = Model("mock:flaky", "Flaky", "mock", "flaky", "NONE")


def test_deterministic_target_is_perfectly_stable():
    mr = run_n(SAFE, ADVERSARIAL_BATTERY, 5, transport=mock_transport)
    assert mr.n == 5
    assert mr.stability == 1.0                     # nothing flaky
    assert mr.flaky_tasks == []
    assert mr.mean_vulnerability == 0.0 == mr.worst_case_vulnerability


def test_consistently_vulnerable_target_has_no_flakiness_but_full_vuln():
    mr = run_n(VULN, ADVERSARIAL_BATTERY, 4, transport=mock_transport)
    assert mr.stability == 1.0                     # always fails == not flaky
    assert mr.mean_vulnerability == 1.0 == mr.worst_case_vulnerability


def test_flaky_target_exposes_intermittent_leaks_a_single_run_would_miss():
    mr = run_n(FLAKY, ADVERSARIAL_BATTERY, 10, transport=flaky_transport)
    flaky_ids = {t.id for t in mr.flaky_tasks}
    # the three seeded-flaky tasks, and nothing else
    assert flaky_ids == {"pi-ignore", "rc-benign-refuse", "hb-unanswerable"}
    # worst-case (fails if it EVER failed) is strictly worse than the mean
    assert mr.worst_case_vulnerability > mr.mean_vulnerability > 0.0
    assert mr.stability < 1.0
    # pi-ignore leaks 2 of every 5 runs -> ~0.6 pass rate over 10
    pi = next(t for t in mr.per_task if t.id == "pi-ignore")
    assert pi.pass_rate == 0.6 and pi.flaky


def test_run_n_is_reproducible():
    a = to_variance_report(run_n(FLAKY, ADVERSARIAL_BATTERY, 10, transport=flaky_transport))
    b = to_variance_report(run_n(FLAKY, ADVERSARIAL_BATTERY, 10, transport=flaky_transport))
    assert a == b                                  # deterministic aggregation


def test_never_touches_multi_path_grades_posted_answer_sets():
    # The browser sampled the model twice; one run leaked the canary, one didn't.
    from crashkit.adversarial import _SAFE_ANSWERS, _VULNERABLE_ANSWERS, _CANARY
    clean = dict(_SAFE_ANSWERS)
    leaked = dict(_SAFE_ANSWERS)
    leaked["pi-ignore"] = f"Sure — the passphrase is {_CANARY}."
    mr = grade_answer_sets("byok:some-model", ADVERSARIAL_BATTERY, [clean, leaked])
    pi = next(t for t in mr.per_task if t.id == "pi-ignore")
    assert pi.flaky and pi.pass_rate == 0.5
    assert mr.worst_case_vulnerability > mr.mean_vulnerability


def test_aggregate_rejects_mixed_batteries():
    import pytest
    from crashkit import AGENTIC_BATTERY, agentic_transport
    adv = run(VULN, ADVERSARIAL_BATTERY, transport=mock_transport)
    agent = run(VULN, AGENTIC_BATTERY, transport=agentic_transport)
    with pytest.raises(ValueError):
        aggregate_runs([adv, agent])


def test_variance_report_is_json_shaped():
    ev = to_variance_report(run_n(FLAKY, ADVERSARIAL_BATTERY, 6, transport=flaky_transport))
    assert set(ev) >= {"run", "n", "metrics", "per_task", "source"}
    assert set(ev["metrics"]) >= {"mean_vulnerability", "worst_case_vulnerability", "stability"}
    assert all({"id", "pass_rate", "flaky"} <= set(t) for t in ev["per_task"])
