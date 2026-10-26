"""
IST post-close EOD ingest scheduler.

Runs once per trading day after configured settle time. Idempotent: skips if a
successful journal row already exists for the expected session. Survives
process restart (checks journal + clock). Manual Refresh / Force full unchanged.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config import config
from app.nse_calendar import expected_eod_as_of, is_trading_day, load_holiday_dates

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_stop = threading.Event()
_state: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "last_tick_ist": None,
    "last_trigger_ist": None,
    "last_result": None,
    "next_eligible_hint": None,
    "error": None,
}


def scheduler_status() -> dict[str, Any]:
    with _lock:
        st = dict(_state)
    holidays, meta = load_holiday_dates()
    now = datetime.now(IST)
    st.update(
        {
            "schedule_enabled": bool(config.eod_ingest_schedule_enabled),
            "time_ist": f"{config.eod_ingest_hour_ist:02d}:{config.eod_ingest_minute_ist:02d}",
            "settle_ist": f"{config.eod_settle_hour_ist:02d}:{config.eod_settle_minute_ist:02d}",
            "timezone": "Asia/Kolkata",
            "today_is_trading_day": is_trading_day(now.date(), holidays=holidays),
            "expected_eod_as_of": expected_eod_as_of(now, holidays=holidays).isoformat(),
            "holiday_list_complete": meta.complete,
            "poll_sec": int(config.eod_ingest_poll_sec),
        }
    )
    return st


def _should_fire(now: datetime) -> tuple[bool, str]:
    holidays, _ = load_holiday_dates()
    if not is_trading_day(now.date(), holidays=holidays):
        return False, "not_a_trading_day"
    hh, mm = config.eod_ingest_hour_ist, config.eod_ingest_minute_ist
    if (now.hour, now.minute) < (hh, mm):
        return False, "before_schedule_time"
    target = expected_eod_as_of(now, holidays=holidays).isoformat()
    from app.ingest_journal import last_successful_for_session

    prior = last_successful_for_session(target)
    if prior:
        return False, f"already_done_for_{target}"
    return True, f"fire_for_{target}"


def _run_scheduled_once() -> dict[str, Any]:
    from app.pipeline import run_incremental_ingest
    from app.store import Database

    holidays, _ = load_holiday_dates()
    now = datetime.now(IST)
    target = expected_eod_as_of(now, holidays=holidays).isoformat()
    logger.info("Scheduled EOD ingest firing for session %s", target)
    result = run_incremental_ingest(
        Database(config.db_path),
        force_full=False,
        trigger="schedule",
        target_session=target,
    )
    return result


def _loop() -> None:
    with _lock:
        _state["running"] = True
        _state["enabled"] = True
    logger.info(
        "EOD ingest scheduler started IST %02d:%02d (poll %ss)",
        config.eod_ingest_hour_ist,
        config.eod_ingest_minute_ist,
        config.eod_ingest_poll_sec,
    )
    while not _stop.is_set():
        try:
            now = datetime.now(IST)
            with _lock:
                _state["last_tick_ist"] = now.isoformat()
                _state["error"] = None
            fire, reason = _should_fire(now)
            with _lock:
                _state["next_eligible_hint"] = reason
            if fire:
                try:
                    result = _run_scheduled_once()
                    with _lock:
                        _state["last_trigger_ist"] = now.isoformat()
                        _state["last_result"] = {
                            "status": result.get("status"),
                            "message": result.get("message"),
                            "target_session": result.get("target_session"),
                            "provider": result.get("source"),
                        }
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Scheduled ingest failed: %s", exc)
                    with _lock:
                        _state["error"] = str(exc)[:240]
                        _state["last_result"] = {"status": "error", "message": str(exc)[:240]}
                    # Backoff after failure before retry eligibility (journal won't have ok)
                    _stop.wait(min(300, max(60, int(config.eod_ingest_poll_sec) * 5)))
                    continue
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scheduler tick error: %s", exc)
            with _lock:
                _state["error"] = str(exc)[:240]
        _stop.wait(max(15, int(config.eod_ingest_poll_sec)))
    with _lock:
        _state["running"] = False
        _state["enabled"] = False
    logger.info("EOD ingest scheduler stopped")


def start_scheduler() -> dict[str, Any]:
    global _thread
    if not config.eod_ingest_schedule_enabled:
        return {"started": False, "reason": "EOD_INGEST_SCHEDULE_ENABLED=false"}
    with _lock:
        if _thread and _thread.is_alive():
            return {"started": False, "reason": "already_running"}
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="eod-ingest-scheduler", daemon=True)
        _thread.start()
    return {"started": True, "status": scheduler_status()}


def stop_scheduler() -> None:
    _stop.set()
    t = _thread
    if t and t.is_alive():
        t.join(timeout=5)


# Test helper — pure decision without firing
def should_run_scheduled_ingest(
    now: datetime,
    *,
    already_succeeded_for: str | None = None,
) -> tuple[bool, str]:
    """Deterministic gate used by unit tests (inject prior success via arg)."""
    holidays, _ = load_holiday_dates()
    if not is_trading_day(now.astimezone(IST).date(), holidays=holidays):
        return False, "not_a_trading_day"
    local = now.astimezone(IST)
    if (local.hour, local.minute) < (
        config.eod_ingest_hour_ist,
        config.eod_ingest_minute_ist,
    ):
        return False, "before_schedule_time"
    target = expected_eod_as_of(local, holidays=holidays).isoformat()
    if already_succeeded_for == target:
        return False, f"already_done_for_{target}"
    return True, f"fire_for_{target}"
