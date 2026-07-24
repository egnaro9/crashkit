"""Produce a crash-test ``eval_run.json`` — the file ``scripts/post_run.py`` ships
to eval-history so a target's vulnerability is tracked over time.

Mock-only and deterministic, so CI records a run with no key: the *safe* mock must
always score 0.0 vulnerability, so a grader regression that breaks it shows up as
a jump in the recorded history — the same regression-guard shape rag-eval-lab uses
for its SciFact numbers. A real target's history comes from BYOK runs posted the
same way; the wire shape (``source="crash_test"`` + ``vulnerability_score``) is
identical.

    python -m crashkit.cli --battery adversarial --profile safe --out crash_run.json
"""
from __future__ import annotations

import argparse
import json
from typing import Optional

from modeldrift.providers import Model

from . import (
    ADVERSARIAL_BATTERY,
    AGENTIC_BATTERY,
    agentic_transport,
    mock_transport,
    run,
    to_eval_run,
)

_BATTERIES = {
    "adversarial": (lambda: ADVERSARIAL_BATTERY, mock_transport),
    "agentic": (lambda: AGENTIC_BATTERY, agentic_transport),
}


def build(battery: str = "adversarial", profile: str = "safe") -> dict:
    """A crash-test eval_run dict for one mock profile — deterministic, no key."""
    if battery not in _BATTERIES:
        raise ValueError(f"unknown battery {battery!r} (one of {list(_BATTERIES)})")
    tasks_fn, transport = _BATTERIES[battery]
    model = Model(f"mock:{profile}", f"Mock ({profile})", "mock", profile, "NONE")
    return to_eval_run(run(model, tasks_fn(), transport=transport))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--battery", default="adversarial", choices=list(_BATTERIES))
    ap.add_argument("--profile", default="safe", help="mock profile: safe | vulnerable")
    ap.add_argument("--out", default="crash_run.json")
    args = ap.parse_args(argv)

    ev = build(args.battery, args.profile)
    with open(args.out, "w") as f:
        json.dump(ev, f, indent=2)
    print(f"wrote {args.out}: vulnerability={ev['metrics']['vulnerability_score']} "
          f"({ev['metrics']['n_cases']:.0f} tasks, source={ev['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
