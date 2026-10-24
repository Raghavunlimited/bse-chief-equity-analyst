"""Shared ingest progress state for UI polling."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "message": "Idle",
    "current": 0,
    "total": 0,
    "percent": 0,
    "source": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
    "result": None,
}


def get_progress() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def reset_progress():
    with _lock:
        _state.update(
            {
                "running": True,
                "phase": "starting",
                "message": "Starting refresh…",
                "current": 0,
                "total": 0,
                "percent": 0,
                "source": None,
                "error": None,
                "started_at": time.time(),
                "finished_at": None,
                "result": None,
            }
        )


def update_progress(
    *,
    phase: Optional[str] = None,
    message: Optional[str] = None,
    current: Optional[int] = None,
    total: Optional[int] = None,
    source: Optional[str] = None,
    error: Optional[str] = None,
):
    with _lock:
        if phase is not None:
            _state["phase"] = phase
        if message is not None:
            _state["message"] = message
        if current is not None:
            _state["current"] = current
        if total is not None:
            _state["total"] = total
        if source is not None:
            _state["source"] = source
        if error is not None:
            _state["error"] = error
        cur = _state["current"]
        tot = _state["total"]
        if tot > 0:
            _state["percent"] = min(99, int(100 * cur / tot))
        elif phase == "done":
            _state["percent"] = 100


def finish_progress(result: Optional[dict] = None, error: Optional[str] = None):
    with _lock:
        _state["running"] = False
        _state["finished_at"] = time.time()
        if error:
            _state["phase"] = "error"
            _state["error"] = error
            _state["message"] = error
            _state["percent"] = _state.get("percent") or 0
        else:
            _state["phase"] = "done"
            _state["message"] = (result or {}).get("message") or "Refresh complete"
            _state["percent"] = 100
            _state["result"] = result
