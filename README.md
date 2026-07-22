# crashkit — AI Crash Test

**Point it at a model, run a battery of tasks, read the deterministic grades.**
No LLM judge — every verdict is a predicate you can rerun and get the same
answer. The adversarial, on-demand counterpart to
[model-drift](https://github.com/egnaro9/model-drift)'s longitudinal board: same
[`gradecore`](https://github.com/egnaro9/gradecore) engine, two lenses.

> **Phase 0 — the interactive slice.** Mock-only and fully offline: the runnable
> dummies are model-drift's two deterministic mocks, so there are no keys and no
> live inference. Real providers (bring-your-own-key, so a visitor's key never
> touches the server) and the net-new adversarial batteries land in Phase 1.

## Run it

```bash
pip install -e ../gradecore -e ../model-drift -e ".[dev]"   # the shared engine + reused suite
uvicorn crashkit.app:app --port 8011
# open http://localhost:8011  — pick a dummy, hit "Run the battery"
```

```
POST /api/run   {model}   run the battery, grade via gradecore, store, return
GET  /api/models          the runnable models (mock-only in Phase 0)
GET  /api/runs            leaderboard — most vulnerable first
GET  /api/runs/{id}       one run with its per-task verdicts
```

## How it fits together

```
model-drift SUITE ──(bool_grader)──▶ gradecore battery
      │                                     │
   mock transport ──────────────────────────┤  run + grade  (crashkit.runner)
                                             ▼
                        eval_run.json wire shape (crashkit.serialize)
                                             ▼
                        SQLite run store  ──▶  /api/runs leaderboard  ──▶  React playground
```

- **`battery.py`** — model-drift's frozen SUITE, each `Task.grade` lifted into
  gradecore via `bool_grader`; the battery fingerprint matches model-drift's own.
- **`runner.py`** — runs the battery over the mock transport, grades through
  gradecore, aggregates accuracy / reliability (truncation rides on reliability,
  off the accuracy line — same rule as model-drift).
- **`serialize.py`** — emits eval-history's `eval_run.json` shape, tagged
  `source="crash_test"` so these runs stay off model-drift's pristine board.
- **`store.py` / `app.py`** — a SQLite run store + the playground/leaderboard API.
- **`frontend/`** — a static React page (no build step).

## The separation guardrail

Crash-test runs are tagged `crash_test` and, from Phase 1, live in a **separate**
database from model-drift's monitoring board — adversarial runs cross-reference
the board read-only and never write to it. Phase 0 stores locally.

```bash
pip install -e ".[dev]" && pytest -q      # incl. a determinism test — a serialized run is byte-stable
```

MIT · by [Erik Hill](https://egnaro9.github.io)
