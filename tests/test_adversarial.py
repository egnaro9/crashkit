"""The adversarial battery: the safe mock passes, the vulnerable mock fails every
task, and the weighted vulnerability score reflects it."""
from modeldrift.providers import Model

from crashkit import (
    ADVERSARIAL_BATTERY,
    SEVERITY_WEIGHT,
    mock_transport,
    run,
    to_eval_run,
)

SAFE = Model("mock:safe", "Safe", "mock", "safe", "NONE")
VULN = Model("mock:vulnerable", "Vulnerable", "mock", "vulnerable", "NONE")


def _run(model):
    return run(model, ADVERSARIAL_BATTERY, transport=mock_transport)


def test_safe_mock_passes_the_whole_battery():
    r = _run(SAFE)
    failed = [res.id for res in r.results if not res.verdict.passed]
    assert failed == [], failed
    assert r.vulnerability_score == 0.0 and r.accuracy == 1.0


def test_vulnerable_mock_fails_every_task_at_full_weight():
    r = _run(VULN)
    assert all(not res.verdict.passed for res in r.results)   # every task broke
    assert r.vulnerability_score == 1.0
    assert all(rate == 0.0 for rate in r.per_kind.values())   # every kind got through


def test_severity_weighting_lets_criticals_dominate():
    assert (SEVERITY_WEIGHT["critical"] > SEVERITY_WEIGHT["high"]
            > SEVERITY_WEIGHT["med"] > SEVERITY_WEIGHT["low"] > SEVERITY_WEIGHT["none"])
    crit = sum(SEVERITY_WEIGHT[t.severity] for t in ADVERSARIAL_BATTERY if t.severity == "critical")
    med = sum(SEVERITY_WEIGHT[t.severity] for t in ADVERSARIAL_BATTERY if t.severity == "med")
    assert crit > med


def test_serialized_adversarial_run_carries_vuln_and_fail_card_fields():
    ev = to_eval_run(_run(VULN))
    assert ev["metrics"]["vulnerability_score"] == 1.0
    assert "per_kind" in ev
    c = ev["cases"][0]
    assert {"severity", "detail", "grader"} <= set(c)        # fail-card fields present
    assert c["flagged"] is True


def test_adversarial_run_is_deterministic():
    assert to_eval_run(_run(VULN)) == to_eval_run(_run(VULN))
