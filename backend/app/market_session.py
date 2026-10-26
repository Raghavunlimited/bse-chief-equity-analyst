"""
NSE cash / FO session clock (IST) + market-data state classification.

Phase 4: weekends + configurable NSE holiday snapshot (see nse_calendar).
Holiday list is operator-maintained JSON — not a live NSE API.

Age policy: during regular hours, quote age > LIVE_QUOTE_STALE_SEC → STALE.
Yahoo/research sources never classify as LIVE — only FALLBACK when age-fresh.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.config import config
from app.market_types import (
    FeedHealth,
    FeedStatus,
    LiveQuote,
    MarketDataState,
    provider_class_for_source,
)

IST = ZoneInfo("Asia/Kolkata")

_OPEN_MIN = 9 * 60 + 15
_CLOSE_MIN = 15 * 60 + 30
_PRE_MIN = 9 * 60  # 09:00

CALENDAR_NOTE = (
    "Session clock: trading days 09:15–15:30 IST. Weekends closed. "
    "Holidays from configurable NSE snapshot (nse_holidays.json / "
    "NSE_EXTRA_HOLIDAYS) — not live-synced from NSE."
)


def now_ist() -> datetime:
    return datetime.now(IST)


def session_snapshot(at: datetime | None = None) -> dict[str, Any]:
    """Canonical session state for APIs and desks."""
    from app.nse_calendar import is_holiday, is_trading_day, is_weekend, load_holiday_dates

    dt = at.astimezone(IST) if at is not None else now_ist()
    weekday = dt.weekday()  # Mon=0 … Sun=6
    minute = dt.hour * 60 + dt.minute
    holidays, meta = load_holiday_dates()
    d = dt.date()
    is_weekday = weekday < 5
    trading = is_trading_day(d, holidays=holidays)
    holiday = is_holiday(d, holidays=holidays)

    if is_weekend(d):
        label = "WEEKEND"
        in_regular = False
        pre_market = False
        status: FeedStatus = "WEEKEND"
        note = "Weekend — live-tick triggers frozen. EOD / last observation only."
    elif holiday:
        label = "HOLIDAY"
        in_regular = False
        pre_market = False
        status = "HOLIDAY"
        note = (
            "NSE holiday (configured calendar) — live ticks frozen. "
            "Verify against current NSE circular if unsure."
        )
    elif not trading:
        label = "HOLIDAY"
        in_regular = False
        pre_market = False
        status = "HOLIDAY"
        note = "Non-trading day per calendar."
    elif minute < _PRE_MIN:
        label = "POST-MARKET"
        in_regular = False
        pre_market = False
        status = "POST_MARKET"
        note = "Before pre-open — POST-MARKET / EOD SNAPSHOT. Live ticks frozen."
    elif _PRE_MIN <= minute < _OPEN_MIN:
        label = "PRE-MARKET"
        in_regular = False
        pre_market = True
        status = "PRE_MARKET"
        note = "NSE pre-open window — live call generation frozen until 09:15 IST."
    elif _OPEN_MIN <= minute <= _CLOSE_MIN:
        label = "REGULAR"
        in_regular = True
        pre_market = False
        status = "LIVE"  # provisional age/provider may still demote
        note = "NSE regular session 09:15–15:30 IST. Broker LIVE only from Kotak WS."
    else:
        label = "POST-MARKET"
        in_regular = False
        pre_market = False
        status = "POST_MARKET"
        note = "After close — POST-MARKET / EOD SNAPSHOT. Live ticks frozen."

    return {
        "in_session": in_regular,
        "in_regular_hours": in_regular,
        "pre_market": pre_market,
        "session_label": label,
        "feed_status_default": status,
        "ist": dt.isoformat(),
        "ist_minute": minute,
        "weekday": weekday,
        "is_weekday": is_weekday,
        "is_trading_day": trading,
        "is_holiday": holiday,
        "open_ist": "09:15",
        "close_ist": "15:30",
        "stale_sec_threshold": float(config.live_quote_stale_sec),
        "note": note,
        "note_legacy": note,
        "calendar_note": CALENDAR_NOTE
        + ("" if meta.complete else " Holiday list incomplete — verify NSE circular."),
        "holiday_calendar_applied": meta.applied,
        "holiday_list_complete": meta.complete,
        "holiday_calendar_source": meta.source,
        "holiday_calendar_as_of": meta.as_of,
        "holiday_calendar_limitation": meta.limitation,
    }


def assess_quote_age(
    quote_ts_unix: float | None,
    *,
    now_unix: float | None = None,
    session: dict[str, Any] | None = None,
) -> tuple[FeedStatus, float, bool]:
    """
    Age gate only (provider-agnostic).

    Returns (age_bucket, age_sec, age_allows_generation).
    age_bucket is LIVE when age-ok in regular hours — caller must still apply
    provider rules via classify_market_data_state (Yahoo → FALLBACK).
    """
    sess = session or session_snapshot()
    now = now_unix if now_unix is not None else datetime.now(timezone.utc).timestamp()
    threshold = float(config.live_quote_stale_sec)

    if quote_ts_unix is None:
        age = float("inf")
    else:
        age = max(0.0, float(now) - float(quote_ts_unix))

    if not sess.get("in_regular_hours"):
        status: FeedStatus = sess.get("feed_status_default") or "POST_MARKET"
        return status, age if age != float("inf") else -1.0, False

    if quote_ts_unix is None:
        return "ERROR", -1.0, False
    if age > threshold:
        return "STALE", age, False
    return "LIVE", age, True


def classify_market_data_state(
    *,
    source: str | None,
    quote_ts_unix: float | None,
    has_ltp: bool,
    error: str | None = None,
    now_unix: float | None = None,
    session: dict[str, Any] | None = None,
) -> tuple[MarketDataState, float, bool, bool]:
    """
    Returns (market_data_state, age_sec, generation_allowed, is_current_broker_live).

    generation_allowed: research desks may emit BUY/SELL (Yahoo FALLBACK ok).
    is_current_broker_live: only Kotak/broker + age-fresh in regular hours.
    """
    sess = session or session_snapshot()
    now = now_unix if now_unix is not None else datetime.now(timezone.utc).timestamp()
    pclass = provider_class_for_source(source)

    if error or not has_ltp:
        age = (
            max(0.0, float(now) - float(quote_ts_unix))
            if quote_ts_unix is not None
            else -1.0
        )
        return "ERROR" if error else "UNAVAILABLE", age, False, False

    age_bucket, age_sec, age_ok = assess_quote_age(
        quote_ts_unix, now_unix=now, session=sess
    )

    if not sess.get("in_regular_hours"):
        label = str(sess.get("session_label") or "")
        if label == "WEEKEND":
            state: MarketDataState = "WEEKEND"
        elif label == "PRE-MARKET":
            state = "PRE_MARKET"
        elif label == "HOLIDAY":
            state = "HOLIDAY"
        else:
            state = "POST_MARKET"
        return state, age_sec, False, False

    if age_bucket == "STALE":
        return "STALE", age_sec, False, False
    if age_bucket == "ERROR":
        return "ERROR", age_sec, False, False

    # Age-fresh during regular hours
    if pclass == "broker":
        return "LIVE", age_sec, True, True
    if pclass == "research_fallback":
        return "FALLBACK", age_sec, True, False
    # Unknown provider — never claim broker LIVE
    return "DELAYED", age_sec, True, False


def annotate_live_quote(
    q: LiveQuote,
    *,
    now_unix: float | None = None,
    session: dict[str, Any] | None = None,
) -> LiveQuote:
    """Return a copy of LiveQuote with truthful market_data_state fields filled."""
    from dataclasses import replace

    sess = session or session_snapshot()
    state, age, _gen, is_live = classify_market_data_state(
        source=q.source,
        quote_ts_unix=q.quote_ts_unix if q.quote_ts_unix else None,
        has_ltp=q.ltp is not None,
        error=q.error,
        now_unix=now_unix,
        session=sess,
    )
    age_out = q.age_sec
    if age is not None and age != float("inf") and age >= 0:
        age_out = float(age)
    return replace(
        q,
        feed_status=state,  # type: ignore[arg-type]
        market_data_state=state,
        age_sec=age_out,
        provider_class=provider_class_for_source(q.source),
        is_current_live=is_live,
        timeframe=q.timeframe or "ltp",
    )


def build_feed_health(
    quotes: list[LiveQuote],
    *,
    session: dict[str, Any] | None = None,
) -> FeedHealth:
    sess = session or session_snapshot()
    threshold = float(config.live_quote_stale_sec)
    ok = stale = err = fallback = 0
    broker_live = False

    for q in quotes:
        state = q.market_data_state or q.feed_status
        if state in ("ERROR", "UNAVAILABLE") or q.ltp is None:
            err += 1
        elif state == "STALE":
            stale += 1
        elif state == "LIVE":
            ok += 1
            broker_live = True
        elif state == "FALLBACK":
            fallback += 1
        elif state in ("DELAYED",):
            fallback += 1
        else:
            # PRE/POST/WEEKEND residue
            stale += 1

    in_reg = bool(sess.get("in_regular_hours"))
    if not in_reg:
        status: FeedStatus = sess.get("feed_status_default") or "POST_MARKET"
        allowed = False
        msg = sess.get("note") or "Outside regular hours — live calls frozen."
        agg_state: MarketDataState = status  # type: ignore[assignment]
    elif err and not ok and not fallback and not stale:
        status = "ERROR"
        agg_state = "ERROR"
        allowed = False
        msg = "Feed ERROR — no usable LTP. Refusing demo fallback."
    elif stale and not ok and not fallback:
        status = "STALE"
        agg_state = "STALE"
        allowed = False
        msg = (
            f"All quotes older than {threshold:.0f}s during market hours — "
            "STALE; last observation kept, call generation halted."
        )
    elif (stale or err) and not ok and not fallback:
        status = "STALE"
        agg_state = "STALE"
        allowed = False
        msg = (
            f"Feed degraded (broker_live={ok} fallback={fallback} "
            f"stale={stale} error={err}). Call generation halted."
        )
    elif ok:
        status = "LIVE"
        agg_state = "LIVE"
        allowed = True
        msg = "Kotak broker LTP healthy — call generation allowed."
    elif fallback:
        status = "FALLBACK"
        agg_state = "FALLBACK"
        allowed = True
        msg = (
            "Yahoo/research FALLBACK tape (age-fresh) — not broker live. "
            "Calls are research-labeled; prefer Kotak WS for LIVE."
        )
    else:
        status = "STALE"
        agg_state = "STALE"
        allowed = False
        msg = "No usable fresh quotes — call generation halted."

    # Partial pollution: if any STALE/ERROR mixed with ok/fallback → halt
    if in_reg and (stale or err) and (ok or fallback):
        allowed = False
        status = "STALE" if stale else status
        agg_state = "STALE" if stale else agg_state
        msg = (
            f"Feed mixed (broker_live={ok} fallback={fallback} "
            f"stale={stale} error={err}). Halting until all quotes are fresh."
        )

    from app.market_types import _iso_z
    import time

    return FeedHealth(
        feed_status=status,
        market_data_state=agg_state,
        in_regular_hours=in_reg,
        session_label=str(sess.get("session_label") or ""),
        stale_sec_threshold=threshold,
        quotes_ok=ok,
        quotes_stale=stale,
        quotes_error=err,
        quotes_fallback=fallback,
        live_calls_allowed=allowed,
        broker_live=broker_live,
        message=msg,
        as_of=_iso_z(time.time()),
        calendar_note=str(sess.get("calendar_note") or CALENDAR_NOTE),
    )


def freeze_live_sides(
    signals: list[dict[str, Any]],
    reason: str,
    *,
    market_data_state: str | None = None,
) -> list[dict[str, Any]]:
    """
    Force LONG/SHORT/BUY/SELL → FLAT/HOLD when generation is halted.

    Preserves last price as an observation with explicit not-current-live flags.
    Never leaves a fresh-looking actionable side.
    """
    state = market_data_state or "STALE"
    out: list[dict[str, Any]] = []
    for s in signals:
        row = dict(s)
        side = str(row.get("side") or "").upper()
        if side in ("LONG", "BUY", "SHORT", "SELL"):
            row["side"] = "FLAT" if side in ("LONG", "SHORT") else "HOLD"
            row["score"] = min(float(row.get("score") or 50), 50.0)
            if row.get("confidence") is not None:
                try:
                    row["confidence"] = min(float(row["confidence"]), 40.0)
                except (TypeError, ValueError):
                    pass
            tags = list(row.get("tags") or [])
            tags = list(
                dict.fromkeys(
                    [*tags, "FEED_HALT", "NO_LIVE_CALL", "LAST_OBSERVATION", state]
                )
            )
            row["tags"] = tags
            thesis = str(row.get("thesis") or "")
            row["thesis"] = f"{thesis} · HALTED: {reason}".strip(" ·")

        # Always annotate observation honesty when halted
        price = row.get("price") if row.get("price") is not None else row.get("entry")
        row["market_data_state"] = row.get("market_data_state") or state
        row["signal_generation"] = "halted"
        row["is_current_live"] = False
        row["is_last_observation"] = price is not None
        row["observation"] = {
            "price": price,
            "is_last_observation": price is not None,
            "is_current_live": False,
            "market_data_state": row["market_data_state"],
            "source": row.get("source") or row.get("quote_source"),
            "age_sec": row.get("quote_age_sec") or row.get("age_sec"),
            "note": "Last observation only — not current live data.",
        }
        # Strip misleading badges
        badge = str(row.get("badge") or "").upper()
        if badge in ("STRONG_BUY", "STRONG_SELL", "BUY", "SELL"):
            row["badge"] = "HOLD"
        out.append(row)
    return out
