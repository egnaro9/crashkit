#!/usr/bin/env bash
# Rebuild the crashkit wheel and re-lock against it.
#
# BOTH steps, always. pywrangler installs binary-only (--no-build), so the
# Worker depends on a built wheel by file path, and uv pins that wheel BY HASH
# in uv.lock. Rebuilding the wheel without re-locking leaves a lockfile
# expecting the old hash, and then every `uv run` fails with
# "Hash mismatch for crashkit @ file://..." before running the command you
# actually asked for. That failure names the wheel, not the lock, so it reads
# like a corrupt build rather than a stale pin.
set -euo pipefail
cd "$(dirname "$0")/.."
# The repo venv, not system python:  lives there. Falls back to whatever
# python3 has it, so this still works on a fresh clone that ran pip install -e ".[dev]".
PY="./.venv/bin/python"; [ -x "$PY" ] || PY="python3"
"$PY" -m build --wheel --outdir worker/dist
cd worker
rm -f uv.lock pylock.toml
uv sync
echo
echo "wheel and lock are in step. sha256:"
shasum -a 256 dist/crashkit-0.1.0-py3-none-any.whl
