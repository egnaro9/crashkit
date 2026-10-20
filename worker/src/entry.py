"""Cloudflare Worker entrypoint for the crashkit playground API.

The app object is crashkit.app:app unchanged. Everything that made it
unrunnable in an isolate was fixed in crashkit/ itself rather than papered over
here, so the Worker and the uvicorn deployment serve the same code:

  * every route handler is `async def`. Starlette offloads a sync handler to a
    threadpool, and an isolate has no threads: `RuntimeError: can't start new
    thread`, on every request, as a 500.
  * RunStore no longer calls uuid.uuid4() while building its in-memory database
    name. That ran at import time, and Workers withholds entropy during isolate
    startup, so the module raised before a single route was registered.

The three static routes (/, /og-cover.png, /favicon.svg) register only when
frontend/ is present on disk, which it is not inside a python_modules bundle.
Cloudflare's static assets binding serves those paths ahead of the Worker, so
the guard in create_app() is already the right behaviour and needs no change.

The run store is per-isolate and in-memory, so the leaderboard resets when an
isolate recycles. That matches how it behaved on the free Render tier; a
durable board waits on spend caps and rate limits.
"""
from workers import WorkerEntrypoint

from crashkit.app import app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi
        return await asgi.fetch(app, request, self.env)
