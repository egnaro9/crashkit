"""crashkit — the crash-test platform backend.

Runs a battery against one model, grades every answer through `gradecore` (whose
verdicts are verified identical to model-drift's own predicates), and serializes the run
to eval-history's wire shape. Two batteries: the model-drift correctness suite,
and the adversarial crash-test with a severity-weighted vulnerability score.
Phase 1 is still mock-only and fully offline.
"""
from .adversarial import (
    BATTERY as ADVERSARIAL_BATTERY,
    CRASHTEST_VERSION,
    AdversarialTask,
    flaky_transport,
    mock_transport,
)
from .agentic import (
    AGENTIC_VERSION,
    BATTERY as AGENTIC_BATTERY,
    AgenticTask,
    agentic_transport,
)
from .battery import BatteryTask, battery_hash, modeldrift_battery
from .retrieval import (
    BATTERY as RETRIEVAL_BATTERY,
    RETRIEVAL_VERSION,
    RetrievalTask,
    retrieval_transport,
)
from .runner import SEVERITY_WEIGHT, Run, TaskResult, grade_answers, run
from .serialize import to_eval_run, to_variance_report
from .variance import (
    MultiRun,
    TaskVariance,
    aggregate_runs,
    grade_answer_sets,
    run_n,
)

__version__ = "0.6.0"

__all__ = [
    "BatteryTask", "modeldrift_battery", "battery_hash",
    "AdversarialTask", "ADVERSARIAL_BATTERY", "CRASHTEST_VERSION",
    "mock_transport", "flaky_transport",
    "AgenticTask", "AGENTIC_BATTERY", "AGENTIC_VERSION", "agentic_transport",
    "RetrievalTask", "RETRIEVAL_BATTERY", "RETRIEVAL_VERSION", "retrieval_transport",
    "Run", "TaskResult", "run", "grade_answers", "SEVERITY_WEIGHT",
    "to_eval_run", "to_variance_report",
    # run-N-times variance
    "MultiRun", "TaskVariance", "aggregate_runs", "run_n", "grade_answer_sets",
]
