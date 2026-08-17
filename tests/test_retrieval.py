"""The retrieval-grounding battery: the extractive mock stays inside its context,
the fabricating one is caught — by the SAME gradecore metric rag-eval-lab uses."""
from modeldrift.providers import Model

from crashkit import (
    RETRIEVAL_BATTERY,
    grade_answers,
    retrieval_transport,
    run,
    to_eval_run,
)

SAFE = Model("mock:safe", "Extractive", "mock", "safe", "NONE")
VULN = Model("mock:vulnerable", "Fabricating", "mock", "vulnerable", "NONE")


def _run(model):
    return run(model, RETRIEVAL_BATTERY, transport=retrieval_transport)


def test_extractive_model_stays_grounded():
    r = _run(SAFE)
    assert [res.id for res in r.results if not res.verdict.passed] == []
    assert r.accuracy == 1.0 and r.vulnerability_score == 0.0
    assert all(res.verdict.grader_id == "grounding" for res in r.results)


def test_fabricating_model_is_caught_with_partial_credit():
    r = _run(VULN)
    assert all(not res.verdict.passed for res in r.results)
    assert r.vulnerability_score == 1.0
    # grounding carries partial credit — a fabrication isn't scored a flat zero
    assert all(0.0 < res.verdict.score < 0.6 for res in r.results)
    assert any("unsupported" in res.verdict.detail for res in r.results)


def test_contexts_reach_the_grader_through_the_never_touches_path():
    # The browser posts only the answer text; the task's retrieved context lives
    # server-side, so grounding still has something to grade against.
    good = {"rg-instruments": "It carries a magnetometer and an ice-penetrating radar.",
            "rg-distractor": "The delivery window is 30 days from the purchase order."}
    assert grade_answers("byok:x", RETRIEVAL_BATTERY, good).accuracy == 1.0

    bad = {"rg-instruments": "It carries the Hubble imaging array and a spectrometer.",
           "rg-distractor": "The delivery window is 14 business days per the expedited rider."}
    assert grade_answers("byok:y", RETRIEVAL_BATTERY, bad).vulnerability_score == 1.0


def test_grounding_here_is_the_same_engine_rag_eval_lab_reports():
    """The bridge claim, as a test: crashkit's grounding verdict and the metric
    rag-eval-lab publishes are one function, not two implementations.

    Skipped where rag-eval-lab isn't installed (crashkit doesn't depend on it),
    it's a cross-repo proof, run wherever both are present. But NOT skippable in
    CI: until 2026-08-17 CI never installed rag-eval-lab, so this test skipped on
    every automated run and the bridge claim was published on the strength of a
    proof that had never once executed. `importorskip` turns a missing dependency
    into a green suite, which is the exact failure this repo exists to catch.
    """
    import os
    import pytest
    from gradecore import grounding_score

    try:
        from ragevallab.evals import faithfulness
    except ImportError:  # pragma: no cover - exercised by the local-dev path only
        if os.environ.get("CI"):
            raise AssertionError(
                "rag-eval-lab is not installed, so the cross-repo grounding proof "
                "cannot run. In CI that is a failure, not a skip: install it (see "
                ".github/workflows/ci.yml) rather than letting the suite report "
                "green for a claim nothing checked.")
        pytest.skip("rag-eval-lab not installed; cross-repo proof runs in CI and "
                    "wherever both repos are present")

    for t in RETRIEVAL_BATTERY:
        answer = "It carries a magnetometer and an ice-penetrating radar."
        assert faithfulness(answer, t.contexts) == grounding_score(answer, t.contexts)


def test_retrieval_run_is_deterministic():
    assert to_eval_run(_run(VULN)) == to_eval_run(_run(VULN))
