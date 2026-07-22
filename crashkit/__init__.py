"""crashkit — the crash-test platform backend.

Runs a battery against one model, grades every answer through `gradecore` (the
same deterministic, no-LLM-judge engine model-drift uses), and serializes the
run to eval-history's wire shape. Phase 0 is mock-only and fully offline.
"""
from .battery import BatteryTask, battery_hash, modeldrift_battery
from .runner import Run, TaskResult, run
from .serialize import to_eval_run

__version__ = "0.1.0"

__all__ = [
    "BatteryTask", "modeldrift_battery", "battery_hash",
    "Run", "TaskResult", "run", "to_eval_run",
]
