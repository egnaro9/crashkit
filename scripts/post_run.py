#!/usr/bin/env python3
"""Ship a crash-test eval_run.json to an eval-history service.

A CI utility, deliberately not part of the package — crashkit produces a run and
knows nothing about where it gets stored. Same pattern (and nearly the same code)
as rag-eval-lab's scripts/post_run.py, on purpose: every project in the eval
stack ships its runs the same way, so the file `eval_run.json` is the only
contract anyone has to learn.

The run posts with `source="crash_test"` and a `vulnerability_score` in metrics
(crashkit's serializer sets both), so eval-history keeps it off the correctness
board while still tracking the score over time.

    python -m crashkit.cli --profile safe --out crash_run.json
    EVAL_HISTORY_WRITE_KEY=... python scripts/post_run.py \
        --url https://eval-history.onrender.com --file crash_run.json

stdlib only, like the rest of the eval stack — no requests, no dependency.

Exits 0 and does nothing when no key is set: forks and pull requests don't get
secrets, and that's a skip, not a failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# The free tier sleeps after ~15 minutes idle and takes ~30-50s to wake, so the
# first attempt is expected to be slow or to fail outright. Retrying is not
# papering over flakiness — it's the documented behaviour of the host.
TIMEOUT = 90
ATTEMPTS = 3
BACKOFF = 20


def post(url: str, key: str, payload: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/runs",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        # A 4xx is the server saying no. Retrying it would just be rude.
        return e.code, e.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, help="base URL of the eval-history service")
    ap.add_argument("--file", default="crash_run.json")
    ap.add_argument("--label", default=None, help="what made this run different")
    ap.add_argument("--git-sha", default=None)
    args = ap.parse_args()

    key = os.environ.get("EVAL_HISTORY_WRITE_KEY", "").strip()
    if not key:
        print("no EVAL_HISTORY_WRITE_KEY set — skipping (forks and PRs have no secrets)")
        return 0

    payload = json.load(open(args.file))
    if payload.get("source") != "crash_test":
        # A guard, not a mutation: posting a non-crash-test run from here would
        # smuggle it onto the wrong board. Fix the producer, don't relabel it.
        print(f"refusing to post: source is {payload.get('source')!r}, not 'crash_test'",
              file=sys.stderr)
        return 1
    if args.label:
        payload["label"] = args.label[:200]
    if args.git_sha:
        payload["git_sha"] = args.git_sha[:40]

    for attempt in range(1, ATTEMPTS + 1):
        try:
            status, body = post(args.url, key, payload)
        except Exception as e:                       # noqa: BLE001 - report, then retry
            status, body = 0, f"{type(e).__name__}: {e}"

        if status == 201:
            print(f"stored: {json.loads(body)['id']}  ({payload.get('label')})")
            return 0
        if 400 <= status < 500:
            print(f"refused with {status}: {body}", file=sys.stderr)
            return 1                                 # our fault; retrying won't fix it

        print(f"attempt {attempt}/{ATTEMPTS} failed ({status or 'no response'}): {body[:120]}",
              file=sys.stderr)
        if attempt < ATTEMPTS:
            print(f"  waiting {BACKOFF}s — the free tier is probably still waking up",
                  file=sys.stderr)
            time.sleep(BACKOFF)

    print("could not reach eval-history", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
