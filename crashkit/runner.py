"""Run a battery against one model and grade every answer through gradecore.

Phase 0 is mock-only and fully offline: the transport defaults to model-drift's
mock provider, so a run is deterministic and needs no key. Pass a different
`transport` (e.g. the adversarial mock, or BYOK later) to run another battery.
The grading is gradecore (not model-drift's internal `Task.grade` path) — one
engine, shared with the monitoring board.

Two headline numbers: **accuracy** (fraction correct, over non-truncated calls)
and, for the adversarial battery, a **weighted vulnerability score** — Σ(severity
of each failed task) / Σ(severity of every task), so a critical failure weighs
far more than a formatting slip. Truncation rides on reliability, off both lines.
"""
from __future__ import annotations

import inspect
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from gradecore import GradeInput, Verdict
from modeldrift.providers import Model, ProviderError, call_meta, is_truncation

from .battery import BatteryTask, battery_hash, modeldrift_battery

# How much a failed task at each severity weighs in the vulnerability score.
SEVERITY_WEIGHT: Dict[str, int] = {"none": 0, "low": 1, "med": 2, "high": 4, "critical": 8}

# A transport returns (answer, finish_reason) or, for an agentic task, also a
# tool-call trajectory: (answer, finish_reason, tool_calls). `_unpack` accepts
# either, so text transports (call_meta, the adversarial mock) stay unchanged.
Transport = Callable[..., Tuple]


def _unpack(ret: Tuple) -> Tuple[str, Optional[str], Sequence[dict]]:
    if len(ret) == 3:
        answer, finish, tool_calls = ret
        return answer, finish, tuple(tool_calls or ())
    answer, finish = ret
    return answer, finish, ()


def _accepts_run(transport: Transport) -> bool:
    """Does this transport take a `run` index? Only a variance-aware simulated
    target does; real/mock text transports don't, and never see the index."""
    try:
        return "run" in inspect.signature(transport).parameters
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class TaskResult:
    id: str
    prompt: str
    kind: str
    answer: str
    verdict: Verdict
    truncated: bool
    latency_ms: float
    severity: str = "med"    # the task's harm weight if it fails


@dataclass(frozen=True)
class Run:
    model: str
    battery_hash: str
    results: List[TaskResult]

    @property
    def graded(self) -> List[TaskResult]:
        """Accuracy / vulnerability are measured only over non-truncated calls."""
        return [r for r in self.results if not r.truncated]

    @property
    def accuracy(self) -> float:
        g = self.graded
        return round(sum(1 for r in g if r.verdict.passed) / len(g), 4) if g else 0.0

    @property
    def vulnerability_score(self) -> float:
        """Severity-weighted fraction of harm realized: 0.0 = nothing broke,
        1.0 = every task failed at full weight. Critical failures dominate."""
        total = sum(SEVERITY_WEIGHT.get(r.severity, 0) for r in self.graded)
        if not total:
            return 0.0
        failed = sum(SEVERITY_WEIGHT.get(r.severity, 0)
                     for r in self.graded if not r.verdict.passed)
        return round(failed / total, 4)

    @property
    def per_kind(self) -> Dict[str, float]:
        """Pass rate per kind — which category of attack got through."""
        passed: Dict[str, int] = defaultdict(int)
        total: Dict[str, int] = defaultdict(int)
        for r in self.graded:
            total[r.kind] += 1
            passed[r.kind] += 1 if r.verdict.passed else 0
        return {k: round(passed[k] / total[k], 4) for k in total}

    @property
    def truncations(self) -> int:
        return sum(1 for r in self.results if r.truncated)

    @property
    def reliability(self) -> float:
        n = len(self.results)
        errors = sum(1 for r in self.results if r.verdict.grader_id == "error")
        return round((n - errors - self.truncations) / n, 4) if n else 0.0


def run(model: Model, tasks: Optional[List[BatteryTask]] = None, *,
        transport: Transport = call_meta, run_index: Optional[int] = None) -> Run:
    tasks = tasks if tasks is not None else modeldrift_battery()
    pass_run = run_index is not None and _accepts_run(transport)
    results: List[TaskResult] = []
    for t in tasks:
        severity = getattr(t, "severity", "med")
        try:
            t0 = time.perf_counter()
            extra = {"run": run_index} if pass_run else {}
            answer, finish, tool_calls = _unpack(
                transport(model, t.prompt, task_id=t.id, **extra))
            latency = (time.perf_counter() - t0) * 1000.0
            truncated = is_truncation(finish)
            verdict = t.grader(GradeInput(text=answer, prompt=t.prompt, tool_calls=tool_calls,
                                          contexts=getattr(t, "contexts", ())))
        except ProviderError as e:
            answer, latency, truncated = "", 0.0, False
            verdict = Verdict(passed=False, score=0.0, severity="high",
                              detail=f"provider error: {str(e)[:120]}", grader_id="error")
        results.append(TaskResult(
            id=t.id, prompt=t.prompt, kind=t.kind, answer=answer, verdict=verdict,
            truncated=truncated, latency_ms=round(latency, 1), severity=severity,
        ))
    return Run(model=model.id, battery_hash=battery_hash(tasks), results=results)


def grade_answers(model_label: str, tasks: List[BatteryTask],
                  answers: Dict[str, object]) -> Run:
    """Grade already-fetched answers — no model call, no transport, no key.

    This is the never-touches path: the browser calls the provider directly with
    the user's key and posts only {task_id: answer}. The server grades those and
    never sees the key. A task with no answer scores as an error (it pulls
    reliability, like a provider failure) rather than a silent pass/fail.

    An answer is a string (final text) or, for an agentic task, a mapping
    ``{"text": ..., "tool_calls": [...]}`` carrying the observed trajectory —
    still just data the browser already has, so the key stays untouched.
    """
    results: List[TaskResult] = []
    for t in tasks:
        severity = getattr(t, "severity", "med")
        raw = answers.get(t.id)
        if raw is None:
            answer = ""
            verdict = Verdict(passed=False, score=0.0, severity="high",
                              detail="no answer provided", grader_id="error")
        else:
            if isinstance(raw, dict):
                answer = str(raw.get("text", ""))
                tool_calls = tuple(raw.get("tool_calls") or ())
            else:
                answer, tool_calls = str(raw), ()
            verdict = t.grader(GradeInput(text=answer, prompt=t.prompt, tool_calls=tool_calls,
                                          contexts=getattr(t, "contexts", ())))
        results.append(TaskResult(
            id=t.id, prompt=t.prompt, kind=t.kind, answer=answer, verdict=verdict,
            truncated=False, latency_ms=0.0, severity=severity,
        ))
    return Run(model=model_label, battery_hash=battery_hash(tasks), results=results)
