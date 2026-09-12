"""The vendored third-party source is exactly its upstream commit.

model-drift is not on a package index, so crashkit used to install it from git
and the git pin was what made "crashkit runs model-drift's frozen suite" true.
Vendoring removes that pin, and nothing else in the suite can tell an edited
vendored file from a faithful one: every battery fingerprint covers id and
prompt only, so a grader predicate in the vendored suite can be loosened to
always-pass with every other check still green.

This is the replacement for the git pin. It is the only assertion that fails on
an edit to crashkit/_vendor, so treat a red here as provenance loss, not as a
stale hash to refresh: re-vendor from upstream rather than re-recording the sum
of whatever is currently on disk.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

VENDOR = pathlib.Path(__file__).resolve().parent.parent / "crashkit" / "_vendor"
MANIFEST = VENDOR / "MODELDRIFT_FIDELITY.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_every_vendored_file_matches_its_recorded_digest():
    for rel, expected in _manifest()["files"].items():
        actual = hashlib.sha256((VENDOR / rel).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{rel} does not match model-drift@{_manifest()['source_commit']}. "
            "The vendored tree is a verbatim copy; re-vendor from upstream "
            "instead of updating this digest.")


def test_the_manifest_covers_every_vendored_python_file():
    # A digest list is only a guard while it is COMPLETE. Without this, a new
    # file dropped into the vendored tree is unlisted, unchecked, and silently
    # importable, and the fidelity test above still passes.
    # Every file, not just *.py: a .so, a .pth or a data file dropped in here
    # would be unlisted, unhashed by the emitter, never cmp'd by the replay,
    # and importable.
    on_disk = {
        str(p.relative_to(VENDOR))
        for p in VENDOR.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.parent != VENDOR   # _vendor/__init__.py and the manifest are ours
    }
    assert on_disk == set(_manifest()["files"]), (
        "the vendored tree and MODELDRIFT_FIDELITY.json disagree about which "
        f"files exist: on disk {sorted(on_disk)}, manifest "
        f"{sorted(_manifest()['files'])}")


def test_the_vendored_suite_is_the_one_crashkit_actually_imports():
    # Fidelity of a file nobody loads proves nothing. Bind the checked bytes to
    # the imported module object, so a stray top-level modeldrift/ or a leftover
    # site-packages install cannot win resolution while this test stays green.
    from crashkit._vendor.modeldrift import suite, providers

    for mod, rel in ((suite, "modeldrift/suite.py"),
                     (providers, "modeldrift/providers.py")):
        assert pathlib.Path(mod.__file__).resolve() == (VENDOR / rel).resolve()
