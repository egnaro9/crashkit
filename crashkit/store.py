"""A tiny SQLite run store for the crash-test leaderboard.

Stores each run's eval_run.json blob plus the fields the leaderboard sorts on.
Phase 0 uses stdlib sqlite3 and is self-contained; Phase 1 points this at a
*separate* eval-history instance (the separation guardrail) reusing the same
wire shape, so crash-test runs never touch model-drift's pristine board.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import List, Optional

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    model        TEXT NOT NULL,
    source       TEXT NOT NULL,
    battery_hash TEXT NOT NULL,
    accuracy      REAL NOT NULL,
    vulnerability REAL,
    reliability   REAL,
    created_at   TEXT NOT NULL,
    eval_run     TEXT NOT NULL          -- the full eval_run.json blob
);
CREATE INDEX IF NOT EXISTS ix_runs_created ON runs(created_at);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, path: str = ":memory:") -> None:
        # Plain ":memory:" is per-connection, and a bare shared-cache name would
        # make every store share one db. A UNIQUE shared-cache name gives each
        # store its own in-memory db, shared across its own connections but
        # isolated from other stores (so tests don't bleed into each other).
        if path == ":memory:":
            self._path = f"file:crashkit-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
        else:
            self._path, self._uri = path, False
        self._keepalive = self._connect() if self._uri else None  # hold the shared db open
        with closing(self._connect()) as c:
            c.executescript(_DDL)
            c.commit()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, uri=self._uri)
        c.row_factory = sqlite3.Row
        return c

    def add(self, eval_run: dict, *, run_id: Optional[str] = None) -> str:
        rid = run_id or uuid.uuid4().hex[:12]
        m = eval_run.get("metrics", {})
        with closing(self._connect()) as c:
            c.execute(
                "INSERT INTO runs (id, model, source, battery_hash, accuracy, "
                "vulnerability, reliability, created_at, eval_run) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, eval_run.get("run", ""), eval_run.get("source", "crash_test"),
                 eval_run.get("git_sha", ""), float(m.get("faithfulness", 0.0)),
                 m.get("vulnerability_score"), m.get("reliability"),
                 _utcnow(), json.dumps(eval_run)),
            )
            c.commit()
        return rid

    def leaderboard(self, limit: int = 50) -> List[dict]:
        """One row per run, most-vulnerable first — the crash-test view is 'what
        broke', so the highest weighted vulnerability (then lowest accuracy) is
        on top."""
        with closing(self._connect()) as c:
            rows = c.execute(
                "SELECT id, model, source, battery_hash, accuracy, vulnerability, "
                "reliability, created_at FROM runs "
                "ORDER BY COALESCE(vulnerability, 0) DESC, accuracy ASC, created_at DESC "
                "LIMIT ?", (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, run_id: str) -> Optional[dict]:
        with closing(self._connect()) as c:
            row = c.execute("SELECT eval_run FROM runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row["eval_run"]) if row else None
