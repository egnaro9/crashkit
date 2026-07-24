"""The CLI produces a crash-test eval_run.json — the file post_run.py ships to
eval-history: source='crash_test', with a vulnerability_score in metrics."""
import json

from crashkit.cli import build, main


def test_build_is_crash_test_shaped_with_a_vulnerability_score():
    ev = build("adversarial", "safe")
    assert ev["source"] == "crash_test"
    assert "vulnerability_score" in ev["metrics"]
    # the safe mock is the CI regression-guard: it must score 0.0
    assert ev["metrics"]["vulnerability_score"] == 0.0
    assert ev["metrics"]["n_cases"] == 8.0


def test_vulnerable_profile_scores_full_vulnerability():
    ev = build("adversarial", "vulnerable")
    assert ev["metrics"]["vulnerability_score"] == 1.0


def test_agentic_battery_is_selectable():
    ev = build("agentic", "vulnerable")
    assert ev["source"] == "crash_test"
    assert ev["metrics"]["vulnerability_score"] == 1.0


def test_main_writes_a_file(tmp_path, capsys):
    out = tmp_path / "crash_run.json"
    rc = main(["--battery", "adversarial", "--profile", "safe", "--out", str(out)])
    assert rc == 0 and out.exists()
    payload = json.loads(out.read_text())
    assert payload["source"] == "crash_test"
    assert payload["metrics"]["vulnerability_score"] == 0.0
    assert "crash_test" in capsys.readouterr().out
