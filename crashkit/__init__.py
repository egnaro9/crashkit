"""crashkit — the crash-test platform backend.

Runs a battery against one model, grades every answer through `gradecore` (the
same deterministic, no-LLM-judge engine model-drift uses), and serializes the run
to eval-history's wire shape. Two batteries: the model-drift correctness suite,
and the adversarial crash-test with a severity-weighted vulnerability score.
Phase 1 is still mock-only and fully offline.
"""
from .adversarial import (
    BATTERY as ADVERSARIAL_BATTERY,
    CRASHTEST_VERSION,
    AdversarialTask,
    mock_transport,
)
from .battery import BatteryTask, battery_hash, modeldrift_battery
from .runner import SEVERITY_WEIGHT, Run, TaskResult, run
from .serialize import to_eval_run

__version__ = "0.2.0"

__all__ = [
    "BatteryTask", "modeldrift_battery", "battery_hash",
    "AdversarialTask", "ADVERSARIAL_BATTERY", "CRASHTEST_VERSION", "mock_transport",
    "Run", "TaskResult", "run", "SEVERITY_WEIGHT", "to_eval_run",
]
