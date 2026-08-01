"""Run the adversarial battery against the deliberately-vulnerable mock.

No API key, no network — the mock transport answers from a fixed profile, so
the fail cards below are reproducible byte-for-byte on any machine. The point
is not that a mock fails; it is that the grader names *which* guarantee broke
and how badly, without a model in the loop to grade it.
"""

import textwrap

from demos._ansi import amber, bar, dim, faint, fg, red, severity, teal
from crashkit import ADVERSARIAL_BATTERY, mock_transport, run
from modeldrift.providers import Model

model = Model("mock:vulnerable", "Mock (vulnerable)", "mock", "vulnerable", "NONE")
r = run(model, ADVERSARIAL_BATTERY, transport=mock_transport)

print(
    dim("battery ")
    + fg(r.battery_hash)
    + dim("  ·  ")
    + fg(f"{len(r.results)} tasks")
    + dim("  ·  ")
    + amber(r.model)
)
print(
    red("VULNERABILITY ", bold=True)
    + red(f"{r.vulnerability_score:.2f}", bold=True)
    + dim("     accuracy ")
    + fg(f"{r.accuracy:.0%}")
    + dim("     reliability ")
    + fg(f"{r.reliability:.0%}")
)
print()

for kind, rate in r.per_kind.items():
    print(f"  {dim(kind.ljust(22))} {bar(rate)} {fg(f'{rate:.0%}'.rjust(4))}")
print()

for t in r.results:
    if t.verdict.passed:
        print(f"  {teal('PASS')}  {fg(t.id)}")
        continue
    # Pad the plain text before colouring — ljust counts escape bytes.
    print(
        "  "
        + red("FAIL", bold=True)
        + dim("  sev ")
        + severity(t.severity.ljust(9))
        + fg(t.id.ljust(24))
        + faint(t.verdict.grader_id)
    )
    detail = textwrap.shorten(t.verdict.detail, width=68, placeholder=" …")
    print("        " + faint(detail, italic=True))
