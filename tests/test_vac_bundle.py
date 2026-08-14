"""The VAC bundle held to the harness standard: a gate must be proven in
both directions. Freshness — the battery and the manifest re-emit
byte-identical to the committed vac/ artifacts, twice over. Liveness —
every refusal is seen firing: a case row whose aggregates no longer match
is refused (the serializer-mutation canary), a twin control off its exact
score is refused, an unchecked artifact's bytes still move the manifest's
sha256 pin, and the stamp's two refusals fire on a throwaway repo. A
freshness gate never seen red cannot be told apart from a gate that never
ran — the absence-assertion lesson, applied to this repo's own bundle.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import emit_vac  # noqa: E402


@pytest.fixture(scope="module")
def battery():
    return emit_vac.run_battery()


# ── freshness: emit twice → byte-identical, and identical to what is committed

def test_battery_is_byte_stable(battery):
    assert emit_vac.run_battery() == battery


def test_battery_reproduces_the_committed_bundle(battery):
    for name, data in battery.items():
        assert (ROOT / "vac" / name).read_bytes() == data, (
            f"vac/{name}: committed bytes are not what the code re-emits — "
            "run `python emit_vac.py` and commit the diff")


def test_committed_bundle_is_closed_and_derived(battery):
    """vac/ holds exactly the eight listed artifacts plus a manifest that
    is a pure function of those bytes and the stamped commit — a
    re-authored number, a stale copy, or a smuggled file all fail."""
    assert sorted(p.name for p in (ROOT / "vac").iterdir()) == sorted(
        [*battery, "vac.json"])
    committed = (ROOT / "vac/vac.json").read_text(encoding="utf-8")
    man = json.loads(committed)
    assert sorted(e["path"] for e in man["evidence"]) == sorted(battery)
    for e in man["evidence"]:
        data = (ROOT / "vac" / e["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e["sha256"]
        assert data == battery[e["path"]]
    regen = emit_vac.build_manifest(battery, man["protocol"]["issuer_commit"])
    assert regen == committed


def test_manifest_is_byte_stable(battery):
    assert emit_vac.build_manifest(battery, "abc1234") == \
        emit_vac.build_manifest(battery, "abc1234")


# ── liveness: every refusal seen firing ─────────────────────────────────────

def _retag(payload: bytes, **edits) -> bytes:
    ev = json.loads(payload)
    ev.update(edits)
    return emit_vac._dumps(ev)


def test_tampered_case_row_is_refused(battery):
    """Flip one failed case to passed and leave everything else at its
    published value: the rows and the metrics now disagree, and the
    emitter refuses rather than deriving a manifest around the cook —
    the canary that distinguishes 'checked and clean' from 'never
    checked'."""
    key = "adversarial_vulnerable.eval_run.json"
    ev = json.loads(battery[key])
    case = next(c for c in ev["cases"] if not c["passed"])
    case["passed"], case["flagged"] = True, False
    with pytest.raises(RuntimeError, match="recompute|disagree"):
        emit_vac.build_manifest({**battery, key: emit_vac._dumps(ev)},
                                "abc1234")


def test_incoherent_flag_is_refused(battery):
    """flagged must equal (not passed and not truncated) row by row —
    a case claiming both 'passed' and 'flagged' is refused by name."""
    key = "adversarial_safe.eval_run.json"
    ev = json.loads(battery[key])
    ev["cases"][0]["flagged"] = True   # passed is True: incoherent
    with pytest.raises(RuntimeError, match="contradicts"):
        emit_vac.build_manifest({**battery, key: emit_vac._dumps(ev)},
                                "abc1234")


def test_twin_control_gate_is_live(battery):
    """Substitute the vulnerable payload under the safe artifact's name —
    internally coherent, correct battery fingerprint, wrong control. The
    twin gate must fire: 0.0 is a REQUIRED reading, not a description."""
    key = "adversarial_safe.eval_run.json"
    swapped = _retag(battery["adversarial_vulnerable.eval_run.json"],
                     run="mock:safe")
    with pytest.raises(RuntimeError, match="twin-control drift"):
        emit_vac.build_manifest({**battery, key: swapped}, "abc1234")


def test_unchecked_artifact_bytes_still_move_the_manifest(battery):
    """The variance report carries no structural check, so its ONLY guard
    is the sha256 pin + replay byte-identity — prove the pin is alive: a
    one-number edit changes the emitted manifest."""
    key = "variance_flaky_n10.report.json"
    ev = json.loads(battery[key])
    ev["metrics"]["mean_vulnerability"] = 0.0
    honest = emit_vac.build_manifest(battery, "abc1234")
    cooked = emit_vac.build_manifest(
        {**battery, key: emit_vac._dumps(ev)}, "abc1234")
    h = {e["path"]: e["sha256"] for e in json.loads(honest)["evidence"]}
    c = {e["path"]: e["sha256"] for e in json.loads(cooked)["evidence"]}
    assert h[key] != c[key]
    assert {k for k in h if h[k] != c[k]} == {key}


# ── the stamp's two refusals, live on a throwaway repo ──────────────────────

def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def toy_repo(tmp_path):
    repo = tmp_path / "r"
    (repo / "crashkit").mkdir(parents=True)
    (repo / "crashkit" / "core.py").write_text("x = 1\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "code")
    return repo


def test_stamp_refuses_a_dirty_tree(toy_repo):
    (toy_repo / "crashkit" / "core.py").write_text("x = 2\n")
    with pytest.raises(RuntimeError, match="refusing to stamp"):
        emit_vac.stamp_code_commit(toy_repo)


def test_stamp_ignores_output_dirt_and_tracks_only_code_commits(toy_repo):
    code = emit_vac.stamp_code_commit(toy_repo)
    # the emitter's own output may be dirty (it is what is being emitted)
    (toy_repo / "vac").mkdir()
    (toy_repo / "vac" / "vac.json").write_text("{}\n")
    assert emit_vac.stamp_code_commit(toy_repo) == code
    # an outputs-only commit must NOT move the stamp: CI re-runs the emitter
    # at the results commit expecting byte-identity, stamp included
    _git(toy_repo, "add", ".")
    _git(toy_repo, "commit", "-qm", "results")
    assert emit_vac.stamp_code_commit(toy_repo) == code
    # a code commit must move it
    (toy_repo / "crashkit" / "core.py").write_text("x = 3\n")
    _git(toy_repo, "add", ".")
    _git(toy_repo, "commit", "-qm", "code2")
    assert emit_vac.stamp_code_commit(toy_repo) != code
