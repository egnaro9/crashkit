"""Calling models — one small function per provider, each gated on its own API key.

A model is only probed if its key is present in the environment. That's the cost
control: set `OPENAI_API_KEY` and you track OpenAI; leave it unset and that row is
skipped, no spend, no error. Start with one model, add more when you want to fund
them. stdlib `urllib` only — no SDKs to pin.

**Temperature is per-model, and that matters.** The current flagships reject a
sampling parameter: Claude Opus 4.8 and GPT-5 return a 400 if you send
`temperature`, so a probe that hardcoded `temperature=0` would make every
flagship look 100% broken. Models that accept it are pinned to 0 for
reproducibility; models that reject it set `temperature=None` and it's omitted.

A `mock` provider (deterministic, no key, no network) exists so the whole
pipeline — probe → grade → store → chart — is testable without spending a cent.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from urllib.parse import urlsplit

TIMEOUT = 60
# Some providers sit behind Cloudflare and reject urllib's default
# "Python-urllib/3.x" agent outright (Groq returns 403 code 1010). Identify
# ourselves like a normal client instead.
USER_AGENT = "model-drift/1.0 (+https://github.com/egnaro9/model-drift)"


@dataclass(frozen=True)
class Model:
    id: str            # the series id in the tracker, e.g. "openai:gpt-5"
    label: str         # display name
    provider: str      # openai | openai-compatible | anthropic | gemini | mock
    model: str         # the provider's model id
    key_env: str       # env var holding the api key
    base_url: Optional[str] = None      # for openai-compatible providers (xAI, Groq, …)
    temperature: Optional[float] = 0.0  # None → omit it (flagships that reject the param)
    # Presentation + comparison metadata. These used to be duplicated in a hand-kept
    # array in dashboard/index.html, which meant adding a model here left it tracked
    # but invisible on the board. The registry is the one source now; the dashboard
    # and the narrative generator both read it.
    group: str = ""                     # the lab, e.g. "OpenAI" — one legend row each
    tier: str = ""                      # heavy | flagship | mid | mini | nano | mock
    color: str = "#8b8b8b"              # legend/series colour

    @property
    def available(self) -> bool:
        return self.provider == "mock" or bool(os.environ.get(self.key_env, "").strip())


class ProviderError(RuntimeError):
    pass


MAX_RETRIES = 4
# Retry these: 429 (rate limit) and 5xx (provider capacity/outage) are transient
# by definition. A 400/401/403/404 is deterministic — retrying just wastes the run.
_RETRYABLE = frozenset({429, 500, 502, 503, 504})
# Per-host request-rate caps (requests/min). Groq's free tier is 30 RPM shared
# across the whole org, so probing two Llama models back-to-back spent the budget
# and 34/35 calls 429'd — a rate limit that read on the board as a 0% "regression".
# Pacing turns that into a handful of retries instead of a wall of failures.
_HOST_RPM = {"api.groq.com": 30}
_last_call: Dict[str, float] = {}


def _throttle(url: str) -> None:
    """Space calls to a rate-capped host so we don't 429 ourselves. State is
    per-host and module-level, so two models on the same provider share the cap."""
    host = urlsplit(url).hostname or ""
    rpm = _HOST_RPM.get(host)
    if not rpm:
        return
    min_gap = 60.0 / rpm
    wait = min_gap - (time.monotonic() - _last_call.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.monotonic()


def _retry_after(err: urllib.error.HTTPError, attempt: int) -> float:
    """How long to wait before a retry: honor the provider's Retry-After header if
    it sent one (Groq's 429 does), else exponential backoff, both capped."""
    ra = err.headers.get("Retry-After") if err.headers else None
    if ra:
        try:
            return min(float(ra), 30.0)
        except ValueError:
            pass
    return min(2.0 ** attempt, 20.0)


def _post(url: str, headers: Dict[str, str], body: dict, *, retries: int = MAX_RETRIES) -> dict:
    payload = json.dumps(body).encode()
    hdrs = {"User-Agent": USER_AGENT, **headers}
    for attempt in range(retries + 1):
        _throttle(url)
        req = urllib.request.Request(url, data=payload, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            # collapse whitespace: providers pretty-print JSON errors, and the newlines
            # break the message across log lines exactly when you need to read it
            text = " ".join(e.read().decode().split())[:300]
            if e.code in _RETRYABLE and attempt < retries:
                time.sleep(_retry_after(e, attempt))
                continue
            raise ProviderError(f"{url} -> {e.code}: {text}")
        except urllib.error.URLError as e:
            raise ProviderError(f"{url} unreachable: {e.reason}")
        except (TimeoutError, json.JSONDecodeError) as e:
            # A socket read timeout raises a bare TimeoutError, which is NOT a
            # URLError - so it escaped every handler here, sailed past probe()'s
            # `except ProviderError`, and killed the whole run. One slow response
            # from one provider discarded eleven models that had already been
            # measured. Everything that can go wrong on the wire has to arrive as a
            # ProviderError, or a run is only as reliable as its flakiest endpoint.
            raise ProviderError(f"{url}: {type(e).__name__}: {e}")
    raise ProviderError(f"{url}: exhausted {retries} retries")  # unreachable; for type-checkers


# ── pure request-body builders (tested directly, no network) ──
def openai_body(m: Model, prompt: str) -> dict:
    body = {"model": m.model, "messages": [{"role": "user", "content": prompt}]}
    if m.temperature is not None:
        body["temperature"] = m.temperature
    return body


def anthropic_body(m: Model, prompt: str) -> dict:
    body = {"model": m.model, "max_tokens": 256, "messages": [{"role": "user", "content": prompt}]}
    if m.temperature is not None:
        body["temperature"] = m.temperature
    return body


def gemini_body(m: Model, prompt: str) -> dict:
    cfg = {} if m.temperature is None else {"temperature": m.temperature}
    return {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}


# Each provider is split raw/text: `_x_raw` returns the provider's full JSON
# response, `_x` extracts just the answer. The split costs nothing on the text
# path (call() is unchanged) and lets identity.py read response metadata — the
# served model id — off the same call shape without re-deriving URLs/headers.
def _openai_raw(m: Model, prompt: str) -> dict:
    base = (m.base_url or "https://api.openai.com/v1").rstrip("/")
    key = os.environ[m.key_env].strip()
    return _post(f"{base}/chat/completions",
                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                 openai_body(m, prompt))


def _openai(m: Model, prompt: str) -> str:
    return _openai_raw(m, prompt)["choices"][0]["message"]["content"]


def _anthropic_raw(m: Model, prompt: str) -> dict:
    key = os.environ[m.key_env].strip()
    return _post("https://api.anthropic.com/v1/messages",
                 {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                 anthropic_body(m, prompt))


def _anthropic(m: Model, prompt: str) -> str:
    return "".join(b.get("text", "") for b in _anthropic_raw(m, prompt).get("content", []))


def _gemini_raw(m: Model, prompt: str) -> dict:
    key = os.environ[m.key_env].strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m.model}:generateContent?key={key}"
    return _post(url, {"Content-Type": "application/json"}, gemini_body(m, prompt))


def _gemini(m: Model, prompt: str) -> str:
    data = _gemini_raw(m, prompt)
    return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])


# Deterministic mock: knows the suite's right answers, for testing without keys.
# `mock-drifted` deliberately fails two tasks, so regression detection is testable.
_MOCK_ANSWERS = {
    "if-one-word": "blue", "if-json": '{"ok": true}', "if-no-preamble": "144",
    "fact-capital": "Tokyo", "fact-element": "Au", "fact-planet": "Mercury",
    "math-order": "23", "math-percent": "30", "reason-older": "25",
    "fmt-list": "2, 4, 6", "extract-year": "1648", "no-overrefuse": "hello",
    # hardened tasks (v2)
    "count-r": "3", "sort-numeric": "2, 4, 10, 33", "reverse-str": "dlrow",
    "multi-step-math": "8", "vowel-json": '{"vowels": 5}', "nth-word": "fox",
    "days-feb-2024": "29", "unit-minutes": "150", "logic-syllogism": "yes",
    "compare-decimals": "9.9",
    # v3
    "fmt-exact-token": "OK", "fmt-csv-nospace": "a,b,c", "fmt-uppercase": "YES",
    "fmt-repeat-join": "alpha-alpha-alpha", "constraint-no-e": "black",
    "count-s-mississippi": "4", "nth-char": "e", "compare-negatives": "-0.05",
    "float-subtract": "0.2", "sort-magnitude": "9, 10, 20, 100",
    "needle-extract": "4417", "json-word-count": '{"n": 4}',
    "no-overrefuse-kill": "signal",
}


def _mock(m: Model, task_id: str) -> str:
    # A task the mock has no answer for scores as a model failure when the
    # *fixture* is what's incomplete — and it would drag the control line down
    # on the public chart. Fail loudly instead; test_probe pins mock:stable at
    # 100%, so an unanswered task can't reach the board unnoticed.
    if task_id and task_id not in _MOCK_ANSWERS:
        raise ProviderError(
            f"the mock has no answer for task {task_id!r} — add it to "
            f"_MOCK_ANSWERS whenever you add a task to the suite")
    ans = _MOCK_ANSWERS.get(task_id, "")
    if m.model == "mock-drifted" and task_id in ("if-json", "math-order"):
        return "I'm not sure I can help with that."  # simulated regression
    return ans


_PROVIDERS: Dict[str, Callable[[Model, str], str]] = {
    "openai": _openai, "openai-compatible": _openai,
    "anthropic": _anthropic, "gemini": _gemini,
}

_PROVIDERS_RAW: Dict[str, Callable[[Model, str], dict]] = {
    "openai": _openai_raw, "openai-compatible": _openai_raw,
    "anthropic": _anthropic_raw, "gemini": _gemini_raw,
}


def call(model: Model, prompt: str, task_id: str = "") -> str:
    """Send one prompt to a model, return its text. Raises ProviderError on failure."""
    if model.provider == "mock":
        return _mock(model, task_id)
    fn = _PROVIDERS.get(model.provider)
    if fn is None:
        raise ProviderError(f"unknown provider {model.provider!r}")
    return fn(model, prompt)


def call_raw(model: Model, prompt: str) -> dict:
    """Like `call`, but returns the provider's full JSON response instead of just
    the answer text — so a caller can read response metadata such as the served
    model id. `identity.py` uses this to catch a silently-swapped backend. The
    mock returns a synthetic response echoing its own id, so the identity check is
    testable without keys or network, same as the rest of the pipeline."""
    if model.provider == "mock":
        return {"model": model.model}
    fn = _PROVIDERS_RAW.get(model.provider)
    if fn is None:
        raise ProviderError(f"unknown provider {model.provider!r}")
    return fn(model, prompt)


# A response that stopped because it hit the token cap, rather than finishing the
# thought: OpenAI "length", Anthropic "max_tokens", Gemini "MAX_TOKENS". A cut-off
# answer is a delivery failure, so it belongs on reliability, not accuracy.
_TRUNCATION_REASONS = {"length", "max_tokens", "max_output_tokens"}


def is_truncation(finish_reason: Optional[str]) -> bool:
    return bool(finish_reason) and finish_reason.strip().lower() in _TRUNCATION_REASONS


def _text_from_raw(provider: str, raw: dict) -> str:
    if provider in ("openai", "openai-compatible"):
        return raw["choices"][0]["message"]["content"]
    if provider == "anthropic":
        return "".join(b.get("text", "") for b in raw.get("content", []))
    if provider == "gemini":
        return "".join(p.get("text", "") for p in raw["candidates"][0]["content"]["parts"])
    raise ProviderError(f"unknown provider {provider!r}")


def _finish_from_raw(provider: str, raw: dict) -> Optional[str]:
    if provider in ("openai", "openai-compatible"):
        return (raw.get("choices") or [{}])[0].get("finish_reason")
    if provider == "anthropic":
        return raw.get("stop_reason")
    if provider == "gemini":
        return (raw.get("candidates") or [{}])[0].get("finishReason")
    return None


def call_meta(model: Model, prompt: str, task_id: str = "") -> "tuple[str, Optional[str]]":
    """Like `call`, but also returns the provider's finish_reason — so the runner
    can fold a truncated answer into reliability instead of scoring a cut-off
    reply as wrong. The mock never truncates, so it returns None.

    Fetches the raw response once and extracts both text and finish_reason from
    it; `call()` (the text-only path) is left untouched.
    """
    if model.provider == "mock":
        return _mock(model, task_id), None
    raw_fn = _PROVIDERS_RAW.get(model.provider)
    if raw_fn is None:
        raise ProviderError(f"unknown provider {model.provider!r}")
    raw = raw_fn(model, prompt)
    return _text_from_raw(model.provider, raw), _finish_from_raw(model.provider, raw)


def _get(url: str, headers: Dict[str, str]) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = " ".join(e.read().decode().split())[:300]
        raise ProviderError(f"{url} -> {e.code}: {body}")
    except urllib.error.URLError as e:
        raise ProviderError(f"{url} unreachable: {e.reason}")


def list_models(m: Model) -> List[str]:
    """The model IDs this provider actually exposes to your key.

    Model IDs churn and vary by account tier — guessing them costs a failed run
    and a confusing 0%. This asks the provider instead.
    """
    key = os.environ[m.key_env].strip()
    if m.provider == "anthropic":
        d = _get("https://api.anthropic.com/v1/models?limit=100",
                 {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return [x["id"] for x in d.get("data", [])]
    if m.provider == "gemini":
        d = _get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=200", {})
        return [x["name"].removeprefix("models/") for x in d.get("models", [])]
    base = (m.base_url or "https://api.openai.com/v1").rstrip("/")
    d = _get(f"{base}/models", {"Authorization": f"Bearer {key}"})
    return [x["id"] for x in d.get("data", [])]


def load_registry(path: Optional[str] = None) -> List[Model]:
    """Load the model registry (models.json). Bundled default is overridable."""
    from pathlib import Path
    p = Path(path) if path else Path(__file__).parent / "models.json"
    return [Model(**m) for m in json.loads(p.read_text(encoding="utf-8"))]
