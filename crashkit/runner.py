"""Run a battery against one model and grade every answer through gradecore.

Phase 0 is mock-only and fully offline: the transport is model-drift's mock
provider, so a run is deterministic and needs no key. The grading is gradecore
(not model-drift's internal `Task.grade` path) — that's the whole point: one
engine, shared with the monitoring board.

Truncation follows the same rule model-drift now uses — a cut-off answer is off
the accuracy line and rides on reliability instead.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from gradecore import GradeInput, Verdict
from modeldrift.providers import Model, ProviderError, call_meta, is_truncation

from .battery import BatteryTask, battery_hash, modeldrift_battery


@dataclass(frozen=True)
class TaskResult:
    id: str
    prompt: str
    kind: str
    answer: str
    verdict: Verdict
    truncated: bool
    latency_ms: float


@dataclass(frozen=True)
class Run:
    model: str
    battery_hash: str
    results: List[TaskResult]

    @property
    def graded(self) -> List[TaskResult]:
        """Accuracy is measured only over non-truncated calls."""
        return [r for r in self.results if not r.truncated]

    @property
    def accuracy(self) -> float:
        g = self.graded
        return round(sum(1 for r in g if r.verdict.passed) / len(g), 4) if g else 0.0

    @property
    def truncations(self) -> int:
        return sum(1 for r in self.results if r.truncated)

    @property
    def reliability(self) -> float:
        n = len(self.results)
        errors = sum(1 for r in self.results if r.verdict.grader_id == "error")
        return round((n - errors - self.truncations) / n, 4) if n else 0.0


def run(model: Model, tasks: Optional[List[BatteryTask]] = None) -> Run:
    tasks = tasks if tasks is not None else modeldrift_battery()
    results: List[TaskResult] = []
    for t in tasks:
        try:
            t0 = time.perf_counter()
            answer, finish = call_meta(model, t.prompt, task_id=t.id)
            latency = (time.perf_counter() - t0) * 1000.0
            truncated = is_truncation(finish)
            verdict = t.grader(GradeInput(text=answer, prompt=t.prompt))
        except ProviderError as e:
            answer, latency, truncated = "", 0.0, False
            verdict = Verdict(passed=False, score=0.0, severity="high",
                              detail=f"provider error: {str(e)[:120]}", grader_id="error")
        results.append(TaskResult(
            id=t.id, prompt=t.prompt, kind=t.kind, answer=answer,
            verdict=verdict, truncated=truncated, latency_ms=round(latency, 1),
        ))
    return Run(model=model.id, battery_hash=battery_hash(tasks), results=results)
