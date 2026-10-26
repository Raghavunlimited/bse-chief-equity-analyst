"""
NSE cash-market trading calendar (IST).

Weekends are always closed. Holidays come from a configurable JSON snapshot
(and optional env extras) — NOT a live NSE API (none verified in this repo).

Operators must keep ``nse_holidays.json`` aligned with the current NSE circular.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

_DEFAULT_FILE = Path(__file__).resolve().parent / "data" / "nse_holidays.json"


@dataclass(frozen=True)
class CalendarMeta:
    source: str
    as_of: str | None
    holiday_count: int
    path: str
    limitation: str
    applied: bool
    complete: bool  # False when holiday list empty / missing (weekends-only)


def _parse_ymd(s: str) -> date:
    return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()


def _extra_from_env() -> set[date]:
    raw = os.getenv("NSE_EXTRA_HOLIDAYS", "").strip()
    out: set[date] = set()
    if not raw:
        return out
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(_parse_ymd(part))
        except ValueError:
            logger.warning("Ignoring invalid NSE_EXTRA_HOLIDAYS entry: %s", part)
    return out


@lru_cache(maxsize=4)
def _load_raw(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.is_file():
        return {
            "source": "missing_file",
            "as_of": None,
            "holidays": [],
            "limitation": (
                f"Holiday file missing at {path}. Weekends closed only — "
                "weekday holidays NOT applied until file is provided."
            ),
        }
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def holidays_file_path() -> Path:
    from app.config import config

    raw = getattr(config, "nse_holidays_file", None)
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (Path(__file__).resolve().parent.parent / p)
    return _DEFAULT_FILE


def load_holiday_dates(*, path: Path | None = None) -> tuple[set[date], CalendarMeta]:
    p = path or holidays_file_path()
    raw = _load_raw(str(p.resolve()) if p.exists() else str(p))
    holidays: set[date] = set()
    for item in raw.get("holidays") or []:
        try:
            if isinstance(item, str):
                holidays.add(_parse_ymd(item))
            elif isinstance(item, dict) and item.get("date"):
                holidays.add(_parse_ymd(str(item["date"])))
        except (TypeError, ValueError):
            continue
    holidays |= _extra_from_env()
    complete = len(holidays) > 0 and str(raw.get("source") or "") != "missing_file"
    meta = CalendarMeta(
        source=str(raw.get("source") or "unknown"),
        as_of=raw.get("as_of"),
        holiday_count=len(holidays),
        path=str(p),
        limitation=str(
            raw.get("limitation")
            or "Operator-maintained holiday snapshot — not live NSE sync."
        ),
        applied=True,  # interface always applied (weekends + configured holidays)
        complete=complete,
    )
    return holidays, meta


def clear_calendar_cache() -> None:
    _load_raw.cache_clear()


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_holiday(d: date, *, holidays: set[date] | None = None) -> bool:
    hs = holidays if holidays is not None else load_holiday_dates()[0]
    return d in hs


def is_trading_day(d: date | str, *, holidays: set[date] | None = None) -> bool:
    if isinstance(d, str):
        d = _parse_ymd(d)
    if is_weekend(d):
        return False
    return not is_holiday(d, holidays=holidays)


def previous_trading_day(
    d: date | str,
    *,
    holidays: set[date] | None = None,
    max_lookback: int = 15,
) -> date:
    if isinstance(d, str):
        d = _parse_ymd(d)
    cur = d - timedelta(days=1)
    for _ in range(max_lookback):
        if is_trading_day(cur, holidays=holidays):
            return cur
        cur -= timedelta(days=1)
    return cur


def next_trading_day(
    d: date | str,
    *,
    holidays: set[date] | None = None,
    max_lookahead: int = 15,
) -> date:
    if isinstance(d, str):
        d = _parse_ymd(d)
    cur = d + timedelta(days=1)
    for _ in range(max_lookahead):
        if is_trading_day(cur, holidays=holidays):
            return cur
        cur += timedelta(days=1)
    return cur


def expected_eod_as_of(
    now: datetime | None = None,
    *,
    settle_hour: int | None = None,
    settle_minute: int | None = None,
    holidays: set[date] | None = None,
) -> date:
    """
    Latest session date whose EOD we expect to have in the DB.

    After settle time on a trading day → that day.
    Otherwise → previous trading day.
    """
    from app.config import config

    dt = now.astimezone(IST) if now is not None else datetime.now(IST)
    sh = int(settle_hour if settle_hour is not None else getattr(config, "eod_settle_hour_ist", 18))
    sm = int(
        settle_minute
        if settle_minute is not None
        else getattr(config, "eod_settle_minute_ist", 30)
    )
    d = dt.date()
    past_settle = (dt.hour, dt.minute) >= (sh, sm)
    if is_trading_day(d, holidays=holidays) and past_settle:
        return d
    if is_trading_day(d, holidays=holidays) and not past_settle:
        return previous_trading_day(d, holidays=holidays)
    # Weekend / holiday
    return previous_trading_day(d, holidays=holidays)


def trading_days_between(
    start: date,
    end: date,
    *,
    holidays: set[date] | None = None,
) -> int:
    """Count of trading days in (start, end] — used as freshness age."""
    if end <= start:
        return 0
    n = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur, holidays=holidays):
            n += 1
        cur += timedelta(days=1)
    return n


def calendar_public_status(*, now: datetime | None = None) -> dict[str, Any]:
    holidays, meta = load_holiday_dates()
    dt = now.astimezone(IST) if now is not None else datetime.now(IST)
    today = dt.date()
    expected = expected_eod_as_of(dt, holidays=holidays)
    return {
        "timezone": "Asia/Kolkata",
        "source": meta.source,
        "as_of": meta.as_of,
        "holiday_count": meta.holiday_count,
        "holidays_file": meta.path,
        "holiday_calendar_applied": meta.applied,
        "holiday_list_complete": meta.complete,
        "limitation": meta.limitation,
        "today_ist": today.isoformat(),
        "today_is_trading_day": is_trading_day(today, holidays=holidays),
        "today_is_holiday": is_holiday(today, holidays=holidays),
        "today_is_weekend": is_weekend(today),
        "expected_eod_as_of": expected.isoformat(),
        "previous_trading_day": previous_trading_day(today, holidays=holidays).isoformat(),
        "note": (
            "Weekends always closed. Holidays from configurable snapshot + "
            "NSE_EXTRA_HOLIDAYS. Not a live NSE feed."
        ),
    }


def iter_trading_days(
    start: date,
    end: date,
    *,
    holidays: set[date] | None = None,
) -> Iterable[date]:
    cur = start
    while cur <= end:
        if is_trading_day(cur, holidays=holidays):
            yield cur
        cur += timedelta(days=1)
