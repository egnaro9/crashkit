"""Run the adversarial battery against the deliberately-vulnerable mock.

No API key, no network — the mock transport answers from a fixed profile, so
the fail cards below are reproducible byte-for-byte on any machine. The point
is not that a mock fails; it is that the grader names *which* guarantee broke
and how badly, without a model in the loop to grade it.
"""

import textwrap

from crashkit import ADVERSARIAL_BATTERY, mock_transport, run
from modeldrift.providers import Model

model = Model("mock:vulnerable", "Mock (vulnerable)", "mock", "vulnerable", "NONE")
r = run(model, ADVERSARIAL_BATTERY, transport=mock_transport)

print(f"battery {r.battery_hash}  ·  {len(r.results)} tasks  ·  {r.model}")
print(
    f"VULNERABILITY {r.vulnerability_score:.2f}"
    f"   accuracy {r.accuracy:.0%}"
    f"   reliability {r.reliability:.0%}"
)
print()
for kind, rate in r.per_kind.items():
    print(f"  {kind:<22} pass {rate:.0%}")
print()
for t in r.results:
    if t.verdict.passed:
        continue
    print(f"  [FAIL sev={t.severity:<8}] {t.id:<22} {t.verdict.grader_id}")
    print(f"      {textwrap.shorten(t.verdict.detail, width=70, placeholder=' …')}")
