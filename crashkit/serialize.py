"""Serialize a Run to eval-history's `eval_run.json` wire shape.

Same shape model-drift's `probe()` emits and eval-history ingests, so the
crash-test run store speaks the format the whole eval stack already understands —
and Phase 1 can POST straight to a (separate) eval-history instance. Additions:
`source` (the discriminator that keeps these runs off model-drift's pristine
board), a **vulnerability_score** in metrics, a **per_kind** breakdown, and
per-case `severity`/`detail` so the frontend can render fail cards.

Every case also carries explicit `kind`/`passed`/`truncated` (not just the
derived `flagged` and a free-text note), so every aggregate in `metrics` and
`per_kind` is recomputable offline from the case rows alone — the contract
vac-protocol's `crashkit-battery-v1` evidence profile verifies. A reader who
must parse a note to re-earn a number has been handed a declaration, not
evidence.
"""
from __future__ import annotations

from .runner import Run
from .variance import MultiRun


def to_eval_run(run: Run, *, source: str = "crash_test") -> dict:
    acc = run.accuracy
    cases = [
        {
            "q": f"[{r.id}] {r.prompt}",
            "answer": r.answer[:500],
            "scores": {
                "faithfulness": r.verdict.score, "precision@k": r.verdict.score,
                "recall@k": r.verdict.score, "citation": r.verdict.score,
            },
            "kind": r.kind,
            "passed": bool(r.verdict.passed),
            "truncated": bool(r.truncated),
            # a truncated call is not an accuracy failure (it's off the line)
            "flagged": (not r.verdict.passed) and (not r.truncated),
            "note": _note(r),
            "severity": r.severity,           # the task's harm weight
            "grader": r.verdict.grader_id,
            "detail": r.verdict.detail,        # what was expected vs. what came back
        }
        for r in run.results
    ]
    return {
        "run": run.model,
        "git_sha": run.battery_hash,          # which frozen battery produced this
        "label": f"crash-test · {source}",
        "source": source,
        "metrics": {
            "faithfulness": acc, "precision@k": acc, "recall@k": acc, "citation_rate": acc,
            "flagged_cases": float(sum(1 for c in cases if c["flagged"])),
            "n_cases": float(len(cases)),
            "reliability": run.reliability,
            "truncations": float(run.truncations),
            "vulnerability_score": run.vulnerability_score,
        },
        "per_kind": run.per_kind,
        "cases": cases,
    }


def _note(r) -> str:
    parts = [r.kind, f"sev={r.verdict.severity}"]
    if r.truncated:
        parts.append("truncated")
    return " · ".join(parts)


def to_variance_report(mr: MultiRun, *, source: str = "crash_test") -> dict:
    """A run-N-times variance report as a JSON-able dict for the API/frontend.

    Leads with the headline gap (mean vs worst-case) and lists every task's
    pass-rate across the N runs, flaky ones flagged — the intermittent failures a
    single run would have missed.
    """
    return {
        "run": mr.model,
        "battery_hash": mr.battery_hash,
        "source": source,
        "n": mr.n,
        "metrics": {
            "mean_vulnerability": mr.mean_vulnerability,
            "worst_case_vulnerability": mr.worst_case_vulnerability,
            "stability": mr.stability,
            "flaky_cases": float(len(mr.flaky_tasks)),
            "n_tasks": float(len(mr.per_task)),
        },
        "per_task": [
            {
                "id": t.id, "kind": t.kind, "severity": t.severity,
                "runs": t.runs, "passes": t.passes,
                "pass_rate": t.pass_rate,
                "flaky": t.flaky,
                "ever_failed": t.ever_failed,
            }
            for t in mr.per_task
        ],
    }
