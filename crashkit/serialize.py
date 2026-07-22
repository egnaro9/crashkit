"""Serialize a Run to eval-history's `eval_run.json` wire shape.

Same shape model-drift's `probe()` emits and eval-history ingests, so the
crash-test run store speaks the format the whole eval stack already understands —
and Phase 1 can POST straight to a (separate) eval-history instance. The one
addition is `source` (default "crash_test"), the discriminator that keeps these
runs off model-drift's pristine board.
"""
from __future__ import annotations

from .runner import Run


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
            # a truncated call is not an accuracy failure (it's off the line)
            "flagged": (not r.verdict.passed) and (not r.truncated),
            "note": _note(r),
        }
        for r in run.results
    ]
    return {
        "run": run.model,
        "git_sha": run.battery_hash,        # which frozen battery produced this
        "label": f"crash-test · {source}",
        "source": source,
        "metrics": {
            "faithfulness": acc, "precision@k": acc, "recall@k": acc, "citation_rate": acc,
            "flagged_cases": float(sum(1 for c in cases if c["flagged"])),
            "n_cases": float(len(cases)),
            "reliability": run.reliability,
            "truncations": float(run.truncations),
        },
        "cases": cases,
    }


def _note(r) -> str:
    parts = [r.kind, f"sev={r.verdict.severity}"]
    if r.truncated:
        parts.append("truncated")
    return " · ".join(parts)
