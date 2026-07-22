"""The crash-test playground + leaderboard API (Phase 1, mock-only).

    GET  /api/batteries          -> the batteries and their runnable models
    GET  /api/models             -> every model (flat) — back-compat
    POST /api/run   {model,battery} -> run, grade via gradecore, store, return
    GET  /api/runs               -> leaderboard (most vulnerable first)
    GET  /api/runs/{id}          -> one run with its per-task verdicts
    GET  /                       -> the static playground

Two batteries: the model-drift correctness **suite**, and the **adversarial**
crash-test. Still mock-only — no keys, no live inference. BYOK real providers
are the next step.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from modeldrift.providers import Model, call_meta

from . import grade_answers
from . import run as run_battery
from . import to_eval_run
from .adversarial import BATTERY as ADVERSARIAL_BATTERY
from .adversarial import mock_transport
from .battery import modeldrift_battery
from .store import RunStore


def _mock(mid: str, label: str, profile: str) -> Model:
    return Model(mid, label, "mock", profile, "NONE")


# A battery bundles its tasks, its transport, and the mock models that run it.
_BATTERIES = {
    "suite": {
        "label": "Correctness suite (model-drift)",
        "tasks": modeldrift_battery,
        "transport": call_meta,
        "models": {
            "mock:stable": _mock("mock:stable", "Mock (stable)", "mock"),
            "mock:drifted": _mock("mock:drifted", "Mock (drifted)", "mock-drifted"),
        },
    },
    "adversarial": {
        "label": "Adversarial crash-test",
        "tasks": lambda: ADVERSARIAL_BATTERY,
        "transport": mock_transport,
        "models": {
            "mock:safe": _mock("mock:safe", "Mock (safe)", "safe"),
            "mock:vulnerable": _mock("mock:vulnerable", "Mock (vulnerable)", "vulnerable"),
        },
    },
}

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class RunRequest(BaseModel):
    model: str = Field(description="a model id from GET /api/batteries")
    battery: str = Field(default="suite", description="'suite' or 'adversarial'")


class GradeRequest(BaseModel):
    """The never-touches path: the browser fetched these answers from the provider
    itself and posts only the text. There is deliberately NO key field — a
    provider key never reaches this server."""
    battery: str = Field(default="adversarial")
    model: str = Field(description="a display label for the run, e.g. 'openai:gpt-4o'")
    answers: dict[str, str] = Field(description="{task_id: answer text}, fetched client-side")


def create_app(store: Optional[RunStore] = None) -> FastAPI:
    app = FastAPI(title="crashkit",
                  summary="AI crash-test — deterministic grading, no LLM judge.")
    app.state.store = store or RunStore(os.environ.get("CRASHKIT_DB", ":memory:"))

    @app.get("/api/batteries")
    def batteries() -> list[dict]:
        return [
            {"id": bid, "label": b["label"],
             "models": [{"id": mid, "name": mm.label} for mid, mm in b["models"].items()]}
            for bid, b in _BATTERIES.items()
        ]

    @app.get("/api/models")
    def models() -> list[dict]:
        return [{"id": mid, "name": mm.label, "battery": bid}
                for bid, b in _BATTERIES.items() for mid, mm in b["models"].items()]

    @app.post("/api/run")
    def do_run(body: RunRequest) -> dict:
        battery = _BATTERIES.get(body.battery)
        if battery is None:
            raise HTTPException(status_code=404, detail=f"unknown battery {body.battery!r}")
        model = battery["models"].get(body.model)
        if model is None:
            raise HTTPException(status_code=404,
                                detail=f"model {body.model!r} not in battery {body.battery!r}")
        eval_run = to_eval_run(
            run_battery(model, battery["tasks"](), transport=battery["transport"]))
        run_id = app.state.store.add(eval_run)
        return {"id": run_id, **eval_run}

    @app.get("/api/battery/{battery_id}")
    def battery_prompts(battery_id: str) -> dict:
        """The prompts for a battery — so the browser can fetch each one from the
        provider directly (BYOK) and post the answers back to /api/grade."""
        b = _BATTERIES.get(battery_id)
        if b is None:
            raise HTTPException(status_code=404, detail=f"unknown battery {battery_id!r}")
        return {"battery": battery_id, "label": b["label"],
                "tasks": [{"id": t.id, "prompt": t.prompt, "kind": t.kind} for t in b["tasks"]()]}

    @app.post("/api/grade")
    def grade(body: GradeRequest) -> dict:
        """Grade answers the browser already fetched — the server never sees a key."""
        b = _BATTERIES.get(body.battery)
        if b is None:
            raise HTTPException(status_code=404, detail=f"unknown battery {body.battery!r}")
        eval_run = to_eval_run(grade_answers(body.model, b["tasks"](), body.answers))
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
