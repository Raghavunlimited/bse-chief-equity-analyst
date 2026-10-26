"""
Options OI visualization — Phase options-data / OI viz.

Provider reality (from desk audit / Phase 2–6):
  - Live CE/PE OI, volume, LTP come only from Kotak Neo WS after
    session login + option-chain activate. Not CI e2e-verified.
  - Scrip-master can list expiries/strikes without a live feed.
  - No alternate options provider is used. Idle chain = unavailable
    (never zero OI / zero PCR as fake data).
  - IV on the desk is model-derived from LTP (Black-76 / BS), not an
    exchange-published IV field.
  - oi_change is session baseline delta (first observation / prev_day_oi),
    not a guaranteed exchange “change in OI” feed field.
  - OI / PCR are descriptive research metrics — not trade signals.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import config

PROVIDER_ID = "kotak_neo_ws"
PROVIDER_E2E_VERIFIED_IN_CI = False

# What each viz field means when present
FIELD_SEMANTICS: dict[str, str] = {
    "strike": "scrip_master_option_strike",
    "expiry": "scrip_master_or_active_chain_expiry",
    "oi": "kotak_ws_quote_oi_when_subscribed",
    "oi_change": "session_delta_vs_baseline_or_prev_day_oi",
    "volume": "kotak_ws_session_volume_when_present",
    "iv": "model_derived_from_ltp_not_exchange_iv",
    "underlying_price": "kotak_ws_preferred_else_labeled_yahoo_or_future",
    "source": "always_kotak_neo_ws_when_chain_active",
    "timestamp": "snapshot_as_of_utc_plus_per_leg_quote_age",
    "freshness": "derived_from_leg_quote_age_vs_LIVE_QUOTE_STALE_SEC",
}


def _field(
    value: Any,
    *,
    available: bool,
    reason: str | None = None,
    semantic: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value if available else None,
        "available": bool(available and value is not None),
        "reason": None if (available and value is not None) else (reason or "missing"),
        "semantic": semantic,
    }


def _leg_freshness(age_sec: Optional[float]) -> dict[str, Any]:
    stale_lim = float(config.live_quote_stale_sec or 5.0)
    if age_sec is None:
        return {
            "status": "unavailable",
            "label": "UNAVAILABLE",
            "age_sec": None,
            "stale_threshold_sec": stale_lim,
        }
    age = float(age_sec)
    if age > stale_lim * 4:
        status, label = "stale", "STALE"
    elif age > stale_lim:
        status, label = "aging", "AGING"
    else:
        status, label = "ok", "FRESH"
    return {
        "status": status,
        "label": label,
        "age_sec": round(age, 2),
        "stale_threshold_sec": stale_lim,
    }


def _normalize_leg(side: dict[str, Any] | None, right: str) -> dict[str, Any]:
    if not side:
        return {
            "right": right,
            "available": False,
            "reason": "leg_not_in_chain_or_no_instrument",
            "ltp": _field(None, available=False, reason="no_leg", semantic=FIELD_SEMANTICS["oi"]),
            "oi": _field(None, available=False, reason="no_leg", semantic=FIELD_SEMANTICS["oi"]),
            "oi_change": _field(
                None, available=False, reason="no_leg", semantic=FIELD_SEMANTICS["oi_change"]
            ),
            "volume": _field(
                None, available=False, reason="no_leg", semantic=FIELD_SEMANTICS["volume"]
            ),
            "iv": _field(None, available=False, reason="no_leg", semantic=FIELD_SEMANTICS["iv"]),
            "iv_pct": _field(None, available=False, reason="no_leg", semantic=FIELD_SEMANTICS["iv"]),
            "freshness": _leg_freshness(None),
            "feed_status": "UNAVAILABLE",
            "trading_symbol": None,
        }
    err = side.get("error")
    oi = side.get("oi")
    oi_chg = side.get("oi_change")
    vol = side.get("volume")
    iv = side.get("iv")
    iv_pct = side.get("iv_pct")
    age = side.get("quote_age_sec")
    feed = side.get("feed_status") or ("ERROR" if err else "UNKNOWN")
    return {
        "right": right,
        "available": oi is not None or side.get("ltp") is not None,
        "reason": err,
        "ltp": _field(
            side.get("ltp"),
            available=side.get("ltp") is not None,
            reason=err or "ltp_missing",
        ),
        "oi": _field(
            oi,
            available=oi is not None,
            reason=err or "oi_not_on_quote",
            semantic=FIELD_SEMANTICS["oi"],
        ),
        "oi_change": _field(
            oi_chg,
            available=oi_chg is not None,
            reason=err or "oi_change_unavailable",
            semantic=FIELD_SEMANTICS["oi_change"],
        ),
        "volume": _field(
            vol,
            available=vol is not None,
            reason=err or "volume_not_on_quote",
            semantic=FIELD_SEMANTICS["volume"],
        ),
        "iv": _field(
            iv,
            available=iv is not None and bool(side.get("greeks_ok", True)),
            reason=(
                "greeks_failed"
                if side.get("greeks_ok") is False
                else (err or "iv_not_derived")
            ),
            semantic=FIELD_SEMANTICS["iv"],
        ),
        "iv_pct": _field(
            iv_pct,
            available=iv_pct is not None,
            reason=err or "iv_pct_unavailable",
            semantic=FIELD_SEMANTICS["iv"],
        ),
        "freshness": _leg_freshness(float(age) if age is not None else None),
        "feed_status": feed,
        "trading_symbol": side.get("trading_symbol"),
        "buildup_label": (side.get("buildup") or {}).get("label"),
        "buildup_note": "descriptive_quadrant_not_a_trade_signal",
    }


def _aggregate_freshness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ages: list[float] = []
    statuses: list[str] = []
    for r in rows:
        for side in ("call", "put"):
            fr = (r.get(side) or {}).get("freshness") or {}
            if fr.get("age_sec") is not None:
                ages.append(float(fr["age_sec"]))
            if fr.get("status"):
                statuses.append(str(fr["status"]))
    if not statuses:
        return {
            "status": "unavailable",
            "label": "UNAVAILABLE",
            "max_age_sec": None,
            "note": "No leg quote ages — chain idle or quotes missing",
        }
    if "stale" in statuses:
        status, label = "stale", "STALE"
    elif "aging" in statuses:
        status, label = "aging", "AGING"
    elif "unavailable" in statuses and "ok" not in statuses:
        status, label = "unavailable", "UNAVAILABLE"
    else:
        status, label = "ok", "FRESH"
    return {
        "status": status,
        "label": label,
        "max_age_sec": round(max(ages), 2) if ages else None,
        "legs_with_age": len(ages),
        "stale_threshold_sec": float(config.live_quote_stale_sec or 5.0),
    }


def _list_expiries_catalog(underlying: str) -> dict[str, Any]:
    """Scrip-master expiry list — catalog only; OI not implied."""
    try:
        from app.kotak.option_chain import pick_expiry
        from app.kotak.scrip_master import get_scrip_master

        sm = get_scrip_master()
        sm.ensure_loaded()
        exps = sm.list_expiries(underlying, kind="OPT", exchange_segment="nse_fo")
        nearest = weekly = monthly = None
        try:
            nearest = pick_expiry(underlying, mode="nearest").isoformat()
            weekly = pick_expiry(underlying, mode="weekly").isoformat()
            monthly = pick_expiry(underlying, mode="monthly").isoformat()
        except LookupError:
            pass
        return {
            "available": bool(exps),
            "expiries": exps,
            "nearest": nearest,
            "weekly": weekly,
            "monthly": monthly,
            "oi_for_listed_expiries": "only_after_activate_for_that_expiry",
            "reason": None if exps else "scrip_master_empty_or_unloadable",
        }
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {
            "available": False,
            "expiries": [],
            "nearest": None,
            "weekly": None,
            "monthly": None,
            "oi_for_listed_expiries": "only_after_activate_for_that_expiry",
            "reason": sanitize_error_text(e),
        }


def unavailable_payload(
    underlying: str,
    *,
    reason: str,
    blocker: str,
) -> dict[str, Any]:
    und = underlying.upper().strip()
    catalog = _list_expiries_catalog(und)
    return {
        "available": False,
        "status": "unavailable",
        "underlying": und,
        "reason": reason,
        "blocker": blocker,
        "provider": PROVIDER_ID,
        "provider_e2e_verified_in_ci": PROVIDER_E2E_VERIFIED_IN_CI,
        "field_semantics": FIELD_SEMANTICS,
        "expiry_catalog": catalog,
        "active_expiry": None,
        "underlying_price": _field(
            None,
            available=False,
            reason="chain_inactive",
            semantic=FIELD_SEMANTICS["underlying_price"],
        ),
        "strikes": [],
        "series": [],
        "call_oi_by_strike": [],
        "put_oi_by_strike": [],
        "expiries_oi_comparison": [
            {
                "expiry": e,
                "oi_available": False,
                "reason": "chain_not_activated_for_expiry",
                "call_oi_total": None,
                "put_oi_total": None,
            }
            for e in (catalog.get("expiries") or [])[:12]
        ],
        "freshness": {
            "status": "unavailable",
            "label": "UNAVAILABLE",
            "max_age_sec": None,
        },
        "analytics_note": (
            "PCR / walls / max-pain are not computed while the chain is inactive. "
            "They are research descriptors, not trade signals."
        ),
        "signal_disclaimer": (
            "Open interest and PCR are descriptive research metrics only — "
            "not standalone trading signals and not order instructions."
        ),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "demo": False,
    }


def build_oi_visualization(underlying: str) -> dict[str, Any]:
    """
    Normalize active-chain snapshot into an OI comparison payload.

    Does not activate the chain. Does not invent OI/IV/volume.
    """
    und = underlying.upper().strip()
    from app.kotak.option_chain import get_option_chain_engine

    eng = get_option_chain_engine()
    st = eng.status(und)
    if not st.get("active"):
        return unavailable_payload(
            und,
            reason="option_chain_inactive",
            blocker=(
                "Requires Kotak Neo session login + "
                "POST /api/kotak/option-chain/activate. "
                "No Yahoo/NSE options fallback is used."
            ),
        )

    try:
        snap = eng.snapshot(und)
    except LookupError:
        return unavailable_payload(
            und,
            reason="option_chain_inactive",
            blocker="Activate chain after Kotak login — no live snapshot.",
        )

    catalog = _list_expiries_catalog(und)
    active_exp = snap.get("expiry")
    series: list[dict[str, Any]] = []
    call_pts: list[dict[str, Any]] = []
    put_pts: list[dict[str, Any]] = []
    strikes: list[float] = []

    for row in snap.get("rows") or []:
        strike = float(row["strike"])
        strikes.append(strike)
        call = _normalize_leg(row.get("ce"), "CE")
        put = _normalize_leg(row.get("pe"), "PE")
        series.append(
            {
                "strike": strike,
                "atm": bool(row.get("atm")),
                "call": call,
                "put": put,
            }
        )
        call_pts.append(
            {
                "strike": strike,
                "oi": call["oi"]["value"],
                "oi_available": call["oi"]["available"],
                "oi_change": call["oi_change"]["value"],
                "volume": call["volume"]["value"],
                "iv_pct": call["iv_pct"]["value"],
            }
        )
        put_pts.append(
            {
                "strike": strike,
                "oi": put["oi"]["value"],
                "oi_available": put["oi"]["available"],
                "oi_change": put["oi_change"]["value"],
                "volume": put["volume"]["value"],
                "iv_pct": put["iv_pct"]["value"],
            }
        )

    call_total = sum(p["oi"] for p in call_pts if p["oi"] is not None)
    put_total = sum(p["oi"] for p in put_pts if p["oi"] is not None)
    any_call_oi = any(p["oi_available"] for p in call_pts)
    any_put_oi = any(p["oi_available"] for p in put_pts)

    expiries_cmp: list[dict[str, Any]] = []
    for e in catalog.get("expiries") or []:
        is_active = str(e)[:10] == str(active_exp)[:10]
        if is_active:
            expiries_cmp.append(
                {
                    "expiry": e,
                    "oi_available": any_call_oi or any_put_oi,
                    "reason": None if (any_call_oi or any_put_oi) else "active_but_no_oi_on_quotes",
                    "call_oi_total": call_total if any_call_oi else None,
                    "put_oi_total": put_total if any_put_oi else None,
                    "active": True,
                }
            )
        else:
            expiries_cmp.append(
                {
                    "expiry": e,
                    "oi_available": False,
                    "reason": "chain_not_activated_for_expiry",
                    "call_oi_total": None,
                    "put_oi_total": None,
                    "active": False,
                }
            )

    spot = snap.get("spot")
    freshness = _aggregate_freshness(series)
    status = "ok" if (any_call_oi or any_put_oi) else "unavailable"
    if freshness.get("status") in ("stale", "aging") and status == "ok":
        status = freshness["status"]

    return {
        "available": status != "unavailable",
        "status": status,
        "underlying": und,
        "reason": None if status != "unavailable" else "no_oi_on_subscribed_legs",
        "blocker": None
        if status != "unavailable"
        else "Quotes subscribed but OI field missing on feed ticks",
        "provider": PROVIDER_ID,
        "provider_e2e_verified_in_ci": PROVIDER_E2E_VERIFIED_IN_CI,
        "field_semantics": FIELD_SEMANTICS,
        "expiry_catalog": catalog,
        "active_expiry": active_exp,
        "atm": snap.get("atm"),
        "wing": snap.get("wing"),
        "underlying_price": _field(
            spot,
            available=spot is not None and float(spot) > 0,
            reason="spot_unresolved",
            semantic=FIELD_SEMANTICS["underlying_price"],
        ),
        "strikes": strikes,
        "series": series,
        "call_oi_by_strike": call_pts,
        "put_oi_by_strike": put_pts,
        "expiries_oi_comparison": expiries_cmp,
        "totals": {
            "call_oi": call_total if any_call_oi else None,
            "put_oi": put_total if any_put_oi else None,
            "call_oi_available": any_call_oi,
            "put_oi_available": any_put_oi,
            "pcr": (put_total / call_total)
            if any_call_oi and any_put_oi and call_total > 0
            else None,
            "pcr_note": (
                "Descriptive put/call OI ratio from available strikes only — "
                "not a trade signal; null when either side missing."
            ),
        },
        "freshness": freshness,
        "source": snap.get("source") or PROVIDER_ID,
        "subscribed": snap.get("subscribed"),
        "analytics_note": (
            "Chain analytics (walls/PCR/max-pain) live on /option-chain snapshot. "
            "This endpoint is OI visualization + field honesty only."
        ),
        "signal_disclaimer": (
            "Open interest and PCR are descriptive research metrics only — "
            "not standalone trading signals and not order instructions."
        ),
        "as_of": snap.get("as_of") or datetime.now(timezone.utc).isoformat(),
        "snapshot_built_unix": time.time(),
        "demo": False,
    }
