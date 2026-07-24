"""The crash-test playground + leaderboard API (Phase 1, mock-only).

    GET  /api/batteries          -> the batteries and their runnable models
    GET  /api/models             -> every model (flat) — back-compat
    POST /api/run   {model,battery} -> run, grade via gradecore, store, return
    GET  /api/runs               -> leaderboard (most vulnerable first)
    GET  /api/runs/{id}          -> one run with its per-task verdicts
    GET  /                       -> the static playground

Four batteries — one per piece of the shared eval system: the model-drift
correctness **suite**, the **adversarial** crash-test, **retrieval** grounding
(the same gradecore metric rag-eval-lab reports), and the **agentic** crash-test
(an agent's tool-call trajectory). Every battery is graded by gradecore and
serializes to eval-history's wire shape.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from modeldrift.providers import Model, call_meta

from . import grade_answers
from . import run as run_battery
from . import to_eval_run
from .adversarial import BATTERY as ADVERSARIAL_BATTERY
from .adversarial import flaky_transport, mock_transport
from .agentic import BATTERY as AGENTIC_BATTERY
from .agentic import agentic_transport
from .battery import modeldrift_battery
from .retrieval import BATTERY as RETRIEVAL_BATTERY
from .retrieval import retrieval_transport
from .serialize import to_variance_report
from .store import RunStore
from .variance import grade_answer_sets, run_n


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
            # a simulated stochastic target — only visible under run-N-times.
            "mock:flaky": _mock("mock:flaky", "Mock (flaky — run ×N)", "flaky"),
        },
    },
    "retrieval": {
        "label": "Retrieval grounding (RAG hallucination)",
        "tasks": lambda: RETRIEVAL_BATTERY,
        "transport": retrieval_transport,
        "models": {
            "mock:safe": _mock("mock:safe", "Mock (extractive)", "safe"),
            "mock:vulnerable": _mock("mock:vulnerable", "Mock (fabricating)", "vulnerable"),
        },
    },
    "agentic": {
        "label": "Agentic crash-test (tool-call trajectory)",
        "tasks": lambda: AGENTIC_BATTERY,
        "transport": agentic_transport,
        "models": {
            "mock:safe": _mock("mock:safe", "Mock agent (safe)", "safe"),
            "mock:vulnerable": _mock("mock:vulnerable", "Mock agent (reckless)", "vulnerable"),
        },
    },
}

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _transport_for(battery: dict, model: Model):
    """The transport a given model runs on. The simulated 'flaky' target runs the
    variance-aware transport (it slips on a subset of runs); everyone else uses
    the battery's default transport."""
    if model.model == "flaky":
        return flaky_transport
    return battery["transport"]


class RunRequest(BaseModel):
    model: str = Field(description="a model id from GET /api/batteries")
    battery: str = Field(default="suite", description="'suite' or 'adversarial'")


class RunMultiRequest(BaseModel):
    """Run a battery N times against one (mock) target and report the variance —
    which failures are intermittent, and how mean vulnerability differs from the
    worst case an attacker actually faces."""
    model: str = Field(description="a model id from GET /api/batteries")
    battery: str = Field(default="adversarial")
    n: int = Field(default=5, ge=1, le=50, description="number of runs")


class GradeMultiRequest(BaseModel):
    """The never-touches N-runs path: the browser sampled the real model N times
    (temperature > 0) and posts N answer-sets. No key field — the key never
    reaches this server."""
    battery: str = Field(default="adversarial")
    model: str = Field(description="a display label for the run")
    answer_sets: list[dict[str, Any]] = Field(
        description="N × {task_id: answer|{text,tool_calls}}, each a client-side run")


class GradeRequest(BaseModel):
    """The never-touches path: the browser fetched these answers from the provider
    itself and posts only the text. There is deliberately NO key field — a
    provider key never reaches this server."""
    battery: str = Field(default="adversarial")
    model: str = Field(description="a display label for the run, e.g. 'openai:gpt-4o'")
    # {task_id: answer}, fetched client-side. An answer is the text, or for an
    # agentic task a {"text", "tool_calls"} object carrying the observed
    # trajectory — still just data the browser has, so the key stays untouched.
    answers: dict[str, Any] = Field(description="{task_id: answer|{text,tool_calls}}, client-side")


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
            run_battery(model, battery["tasks"](), transport=_transport_for(battery, model)))
        run_id = app.state.store.add(eval_run)
        return {"id": run_id, **eval_run}

    @app.post("/api/run-multi")
    def do_run_multi(body: RunMultiRequest) -> dict:
        """Run a battery N times against a mock target and return the variance
        report (mean vs worst-case, flaky tasks). Not stored on the leaderboard —
        the board tracks single-run vulnerability; this is a stability probe."""
        battery = _BATTERIES.get(body.battery)
        if battery is None:
            raise HTTPException(status_code=404, detail=f"unknown battery {body.battery!r}")
        model = battery["models"].get(body.model)
        if model is None:
            raise HTTPException(status_code=404,
                                detail=f"model {body.model!r} not in battery {body.battery!r}")
        mr = run_n(model, battery["tasks"](), body.n,
                   transport=_transport_for(battery, model))
        return to_variance_report(mr)

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

    @app.post("/api/grade-multi")
    def grade_multi(body: GradeMultiRequest) -> dict:
        """Grade N client-side answer-sets and report the variance — the
        never-touches path for run-N-times. Still no key here."""
        b = _BATTERIES.get(body.battery)
        if b is None:
            raise HTTPException(status_code=404, detail=f"unknown battery {body.battery!r}")
        if not body.answer_sets:
            raise HTTPException(status_code=400, detail="answer_sets must be non-empty")
        mr = grade_answer_sets(body.model, b["tasks"](), body.answer_sets)
        return to_variance_report(mr)

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
