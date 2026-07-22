"""The crash-test playground + leaderboard API (Phase 0, mock-only).

    POST /api/run     {model}   -> run the battery, grade via gradecore, store, return
    GET  /api/models             -> the runnable models (mock-only in Phase 0)
    GET  /api/runs               -> leaderboard (worst accuracy first)
    GET  /api/runs/{id}          -> one run with its per-task verdicts
    GET  /                       -> the static playground

Fully offline: the only models are the deterministic mocks, so there are no keys
and no live inference. BYOK + real providers land in Phase 1.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from modeldrift.providers import Model

from . import run as run_battery
from . import to_eval_run
from .store import RunStore

# Phase 0 is mock-only: two deterministic controls, no keys.
_MODELS = {
    "mock:stable": Model("mock:stable", "Mock (stable)", "mock", "mock", "NONE"),
    "mock:drifted": Model("mock:drifted", "Mock (drifted)", "mock", "mock-drifted", "NONE"),
}

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class RunRequest(BaseModel):
    model: str = Field(description="a model id from GET /api/models")


def create_app(store: Optional[RunStore] = None) -> FastAPI:
    app = FastAPI(title="crashkit",
                  summary="AI crash-test — deterministic grading, no LLM judge.")
    app.state.store = store or RunStore(os.environ.get("CRASHKIT_DB", ":memory:"))

    @app.get("/api/models")
    def models() -> list[dict]:
        return [{"id": mid, "name": m.label} for mid, m in _MODELS.items()]

    @app.post("/api/run")
    def do_run(body: RunRequest) -> dict:
        m = _MODELS.get(body.model)
        if m is None:
            raise HTTPException(status_code=404, detail=f"unknown model {body.model!r}")
        eval_run = to_eval_run(run_battery(m))
        run_id = app.state.store.add(eval_run)
        return {"id": run_id, **eval_run}

    @app.get("/api/runs")
    def leaderboard() -> list[dict]:
        return app.state.store.leaderboard()

    @app.get("/api/runs/{run_id}")
    def one(run_id: str) -> dict:
        eval_run = app.state.store.get(run_id)
        if eval_run is None:
            raise HTTPException(status_code=404, detail="no such run")
        return {"id": run_id, **eval_run}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    index = _FRONTEND / "index.html"
    if index.exists():
        @app.get("/")
        def home() -> FileResponse:
            return FileResponse(index)

    return app


app = create_app()
