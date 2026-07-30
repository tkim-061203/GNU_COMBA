"""Record which model actually produced a benchmark/summary run.

Benchmark artifacts historically stored only trials/timestamp, never the model,
so old-vs-new comparisons were guesswork. This queries the running LLM servers
(`/v1/models`), whose `root` field carries the real checkpoint path, and returns
a compact provenance dict. All failures are captured, never raised, so it can be
called from any writer without risk of breaking a run.
"""
from __future__ import annotations

import json
import os
import urllib.request


def _probe(base_url: str, timeout: float = 3.0) -> dict:
    """Query a single OpenAI-compatible endpoint's /models and extract identity."""
    url = base_url.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        card = (data.get("data") or [{}])[0]
        path = card.get("root") or ""
        return {
            "served_name": card.get("id"),
            "path": path or None,
            # basename of the checkpoint dir — the human-meaningful model id
            "model": os.path.basename(path.rstrip("/")) if path else card.get("id"),
        }
    except Exception as e:  # network down, bad JSON, timeout, …
        return {"error": f"{type(e).__name__}: {e}"}


def probe_served_models(urls: dict | None = None, timeout: float = 3.0) -> dict:
    """Return {role: {served_name, path, model}} for the generator/debugger
    endpoints. URLs default to LLM_BASE_URL / LLM_DEBUGGER_URL from the env."""
    if urls is None:
        gen = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
        # default must match llm_interface.py: debugger lives on :8001, not gen
        dbg = os.environ.get("LLM_DEBUGGER_URL", "http://localhost:8001/v1")
        urls = {"generator": gen, "debugger": dbg}
    return {role: _probe(u, timeout) for role, u in urls.items()}


if __name__ == "__main__":  # quick manual check
    print(json.dumps(probe_served_models(), indent=2))
