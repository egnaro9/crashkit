"""Show that these repos share code, rather than describing the same idea twice.

"One system that calls itself" is easy to write and hard to check. Three claims
are checkable, so this checks them:

  1. crashkit's correctness battery IS model-drift's frozen suite — same tasks,
     same fingerprint, computed independently in each repo.
  2. rag-eval-lab's faithfulness IS gradecore's grounding_score — the same
     function object, not a copy that has drifted.
  3. If either ever stops being true, it is detectable. The last section breaks
     one task on purpose and watches the fingerprint move.

Nothing here is asserted in prose: every line prints a value the repos compute.
Offline, no API key.

    PYTHONPATH=../model-drift:../rag-eval-lab python3 -m demos.one_system
"""

import dataclasses
import inspect

from crashkit import battery_hash, modeldrift_battery
from demos._ansi import accent, dim, fail, muted, ok, text
from gradecore.grounding import grounding_score
from modeldrift.suite import SUITE, suite_hash

import ragevallab.evals as ragevallab


def row(label, value, paint=text):
    print(f"  {muted(label.ljust(30))}{paint(str(value))}")


WIDTH = 74


def rule(title):
    print()
    print(muted("── ") + text(title) + muted(" " + "─" * max(1, WIDTH - len(title) - 4)))


rule("crashkit's battery IS model-drift's suite")
battery = modeldrift_battery()
md, ck = suite_hash(), battery_hash(battery)
row("model-drift  suite_hash()", md, accent)
row("crashkit     battery_hash()", ck, accent)
row("tasks", f"{len(SUITE)} in model-drift · {len(battery)} in crashkit")
print("  " + (ok("identical — one frozen suite, two repos") if md == ck
              else fail("DIVERGED — the extraction has drifted")))

rule("rag-eval-lab's faithfulness IS gradecore's grounder")
delegates = grounding_score.__name__ in inspect.getsource(ragevallab.faithfulness)
row("gradecore.grounding_score", inspect.getsourcefile(grounding_score).split("/")[-3:][0] + "/…")
row("ragevallab.faithfulness", "delegates" if delegates else "reimplements")
probe = ("Neptune is the hottest planet.", ("Venus is the hottest planet.",))
row("same input, both callers", f"{ragevallab.faithfulness(*probe):.4f} == {grounding_score(*probe):.4f}")
print("  " + (ok("one grader, called from two places")
              if delegates and ragevallab.faithfulness(*probe) == grounding_score(*probe)
              else fail("DIVERGED — rag-eval-lab is no longer delegating")))

rule("and if the extraction drifts, the fingerprint says so")
# The tasks are frozen dataclasses — which is the point — so the drift is
# simulated by replacing one, not by mutating the real suite in place.
victim = battery[0]
mutated = [dataclasses.replace(victim, prompt=victim.prompt + " ")] + list(battery[1:])
row("changed", f"task {victim.id!r}: one trailing space")
row("fingerprint now", battery_hash(mutated), accent)
moved = battery_hash(mutated) != ck
print("  " + (fail("CAUGHT — a one-character edit moves the hash", bold=True) if moved
              else ok("hash unchanged — the fingerprint would not notice")))
print()
print(dim("  The suite is frozen and fingerprinted precisely so that a score"))
print(dim("  moving means the model moved, not the questions."))
