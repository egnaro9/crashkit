"""The crash-test battery.

Phase 0 reuses model-drift's *frozen* SUITE, lifted into a gradecore-gradeable
battery: each model-drift `Task.grade` (a `Callable[[str], bool]`) is wrapped
with `gradecore.bool_grader`, so the exact frozen questions run through the
shared engine and nothing about the SUITE is rewritten. The battery hash matches
model-drift's own fingerprint for that SUITE.

Phase 1 adds the net-new adversarial batteries (injection, tool-misuse,
spec-violation, refusal-calibration); this is deliberately the reuse slice.
"""
from __future__ import annotations

from dataclasses import dataclass

from gradecore import Grader, bool_grader, suite_hash


@dataclass(frozen=True)
class BatteryTask:
    id: str
    prompt: str
    kind: str
    grader: Grader


def modeldrift_battery() -> list[BatteryTask]:
    """model-drift's frozen SUITE as a gradecore battery (imported lazily so the
    dependency is only needed when this battery is actually built)."""
    from modeldrift.suite import SUITE

    return [
        BatteryTask(id=t.id, prompt=t.prompt, kind=t.kind,
                    grader=bool_grader(t.grade, grader_id=t.kind))
        for t in SUITE
    ]


def battery_hash(tasks: list[BatteryTask]) -> str:
    """Freeze fingerprint of a battery — same construction as model-drift's
    suite_hash, so the reused SUITE fingerprints identically."""
    return suite_hash(f"{t.id}:{t.prompt}" for t in tasks)
