"""Run-N-times variance — catching the *intermittent* failure.

A single crash-test run against a real (stochastic) model can get lucky: a target
that leaks one time in five looks clean four runs out of five. gradecore's grader
is deterministic — but the *target* isn't — so run the frozen battery N times and
aggregate. The story is the gap between two numbers:

  - **mean vulnerability**  : the average over the N runs — what one run expects.
  - **worst-case**          : a task counts as failed if it failed in ANY run —
                              the honest security posture, because an attacker
                              only needs the leak to land once.

Plus the **flaky** tasks: those that neither always passed nor always failed. A
single run would have silently missed them. The aggregation itself is pure and
deterministic — same N runs in, same report out — so only the target introduces
variance, never the measurement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from modeldrift.providers import Model, call_meta

from .battery import BatteryTask
from .runner import SEVERITY_WEIGHT, Run, Transport, grade_answers, run


@dataclass(frozen=True)
class TaskVariance:
    id: str
    kind: str
    severity: str
    runs: int          # how many runs graded this task (truncations excluded)
    passes: int

    @property
    def pass_rate(self) -> float:
        return round(self.passes / self.runs, 4) if self.runs else 0.0

    @property
    def ever_failed(self) -> bool:
        return self.passes < self.runs

    @property
    def flaky(self) -> bool:
        """Neither always passed nor always failed — a single run is a coin flip."""
        return 0 < self.passes < self.runs


@dataclass(frozen=True)
class MultiRun:
    model: str
    battery_hash: str
    n: int
    per_task: List[TaskVariance]
    mean_vulnerability: float          # average vulnerability_score over the N runs
    worst_case_vulnerability: float    # a task fails if it failed in ANY run

    @property
    def flaky_tasks(self) -> List[TaskVariance]:
        return [t for t in self.per_task if t.flaky]

    @property
    def stability(self) -> float:
        """1.0 = every task was consistent across the N runs; lower = more flaky."""
        if not self.per_task:
            return 1.0
        return round(1 - len(self.flaky_tasks) / len(self.per_task), 4)


def aggregate_runs(runs: List[Run]) -> MultiRun:
    """Fold N single Runs of the *same battery* into a variance report."""
    if not runs:
        raise ValueError("aggregate_runs needs at least one run")
    hashes = {r.battery_hash for r in runs}
    if len(hashes) != 1:
        raise ValueError(f"runs are from different batteries: {sorted(hashes)}")

    passes: Dict[str, int] = {}
    counts: Dict[str, int] = {}
    meta: Dict[str, tuple] = {}       # id -> (kind, severity)
    order: List[str] = []
    for r in runs:
        for res in r.graded:          # graded == non-truncated
            if res.id not in counts:
                order.append(res.id)
                counts[res.id] = passes[res.id] = 0
                meta[res.id] = (res.kind, res.severity)
            counts[res.id] += 1
            passes[res.id] += 1 if res.verdict.passed else 0

    per_task = [
        TaskVariance(id=i, kind=meta[i][0], severity=meta[i][1],
                     runs=counts[i], passes=passes[i])
        for i in order
    ]

    mean_vuln = round(sum(r.vulnerability_score for r in runs) / len(runs), 4)

    total_w = sum(SEVERITY_WEIGHT.get(t.severity, 0) for t in per_task)
    failed_w = sum(SEVERITY_WEIGHT.get(t.severity, 0) for t in per_task if t.ever_failed)
    worst = round(failed_w / total_w, 4) if total_w else 0.0

    return MultiRun(model=runs[0].model, battery_hash=runs[0].battery_hash,
                    n=len(runs), per_task=per_task,
                    mean_vulnerability=mean_vuln, worst_case_vulnerability=worst)


def run_n(model: Model, tasks: List[BatteryTask], n: int, *,
          transport: Transport = call_meta) -> MultiRun:
    """Run a battery N times and aggregate. A deterministic target yields
    stability 1.0 (nothing varies); a stochastic one exposes its flaky tasks.
    The run index is passed to variance-aware transports (see `_accepts_run`)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    return aggregate_runs([run(model, tasks, transport=transport, run_index=i)
                           for i in range(n)])


def grade_answer_sets(model_label: str, tasks: List[BatteryTask],
                      answer_sets: List[Dict[str, object]]) -> MultiRun:
    """The never-touches N-runs path: the browser sampled the real model N times
    (temperature > 0) and posts N answer-sets; the server grades each set
    deterministically and aggregates. No key, no model call here."""
    if not answer_sets:
        raise ValueError("grade_answer_sets needs at least one answer set")
    return aggregate_runs([grade_answers(model_label, tasks, a) for a in answer_sets])
