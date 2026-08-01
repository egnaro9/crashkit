"""Run the adversarial battery against the deliberately-vulnerable mock.

No API key, no network — the mock transport answers from a fixed profile, so
the fail cards below are reproducible byte-for-byte on any machine. The point
is not that a mock fails; it is that the grader names *which* guarantee broke
and how badly, without a model in the loop to grade it.
"""

import textwrap

from crashkit import ADVERSARIAL_BATTERY, mock_transport, run
from demos._ansi import accent, bar, dim, fail, muted, ok, quote, severity, text
from modeldrift.providers import Model

model = Model("mock:vulnerable", "Mock (vulnerable)", "mock", "vulnerable", "NONE")
r = run(model, ADVERSARIAL_BATTERY, transport=mock_transport)

print(
    muted("battery ")
    + text(r.battery_hash)
    + muted("  ·  ")
    + text(f"{len(r.results)} tasks")
    + muted("  ·  ")
    + accent(r.model)
)
print(
    fail("VULNERABILITY ", bold=True)
    + fail(f"{r.vulnerability_score:.2f}", bold=True)
    + muted("     accuracy ")
    + text(f"{r.accuracy:.0%}")
    + muted("     reliability ")
    + text(f"{r.reliability:.0%}")
)
print()

for kind, rate in r.per_kind.items():
    print(f"  {muted(kind.ljust(22))} {bar(rate)} {text(f'{rate:.0%}'.rjust(4))}")
print()

for t in r.results:
    if t.verdict.passed:
        print(f"  {ok('PASS')}  {text(t.id)}")
        continue
    # Pad the plain text before colouring — ljust counts escape bytes.
    print(
        "  "
        + fail("FAIL", bold=True)
        + muted("  sev ")
        + severity(t.severity.ljust(9))
        + text(t.id.ljust(24))
        + dim(t.verdict.grader_id)
    )
    print("        " + quote(textwrap.shorten(t.verdict.detail, width=68, placeholder=" …")))
