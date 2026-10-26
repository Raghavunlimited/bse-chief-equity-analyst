"""
Intraday equity bias signals — research only.

Uses near-live 5m Yahoo quotes for liquid NSE names.
Rules (desk-style, not a profit promise):
- Session bias vs open / prev close
- Session VWAP from 5m close×volume when bar volume exists (else skip / VWAP_PROXY)
- Momentum (last bars slope)
- ORB-lite: break of first-hour high/low when enough bars exist
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import live_quotes
from app.market_session import build_feed_health, freeze_live_sides, session_snapshot
from app.market_types import LiveQuote
from app.strategy.intraday_core import (
    STRATEGY_ID as INTRADAY_STRATEGY_ID,
    STRATEGY_VERSION as INTRADAY_STRATEGY_VERSION,
    rsi as _rsi,
    score_intraday_bias,
    session_vwap as _session_vwap,
)

# Liquid NSE watchlist (Yahoo .NS)
DEFAULT_WATCH = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "BHARTIARTL",
    "LT",
    "AXISBANK",
    "KOTAKBANK",
    "BAJFINANCE",
    "MARUTI",
    "TMPV",  # Tata Motors PV (Yahoo); legacy TATAMOTORS may 404
    "TATASTEEL",
    "SUNPHARMA",
    "HCLTECH",
    "WIPRO",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "ADANIENT",
    "ADANIPORTS",
    "ULTRACEMCO",
    "TITAN",
]


def _signal_for(symbol: str, snap: dict[str, Any] | LiveQuote) -> dict[str, Any]:
    if isinstance(snap, LiveQuote):
        snap = snap.to_dict()
    price = snap.get("price") or snap.get("ltp")
    opens = snap.get("session_open")
    high = snap.get("session_high")
    low = snap.get("session_low")
    prev = snap.get("prev_close")
    closes = list(snap.get("closes_5m") or [])
    volumes = list(snap.get("volumes_5m") or [])
    change = snap.get("change_pct")
    feed_status = snap.get("feed_status")
    age_sec = snap.get("age_sec")

    mds = snap.get("market_data_state") or feed_status
    src = snap.get("source")
    if price is None or feed_status == "ERROR" or mds in ("ERROR", "UNAVAILABLE"):
        return {
            "symbol": symbol,
            "side": "FLAT",
            "score": 0,
            "thesis": f"Quote ERROR — {snap.get('error') or 'no LTP'} (no demo fallback)",
            "tags": ["NO_QUOTE", "FEED_ERROR"],
            "price": None,
            "price_kind": "ltp",
            "feed_status": "ERROR",
            "market_data_state": "ERROR",
            "source": src,
            "quote_source": src,
            "quote_age_sec": age_sec,
            "is_current_live": False,
            "timeframe": snap.get("timeframe") or "ltp",
            "strategy_id": INTRADAY_STRATEGY_ID,
            "strategy_version": INTRADAY_STRATEGY_VERSION,
        }

    core = score_intraday_bias(
        price=float(price),
        closes_5m=closes,
        volumes_5m=volumes,
        change_pct=float(change) if change is not None else None,
        session_open=float(opens) if opens is not None else None,
        session_high=float(high) if high is not None else None,
        session_low=float(low) if low is not None else None,
    )
    side = core["side"]
    score = core["score"]
    tags = list(core["tags"])
    rsi = core["rsi_5m"]
    vwap = core["vwap"]
    stop = core["stop"]
    target = core["target"]

    thesis_bits = [
        f"{side} bias @ ₹{price:,.2f}",
        f"day {change:+.2f}%" if change is not None else None,
        f"RSI {rsi}" if rsi is not None else None,
        ", ".join(tags[:4]) if tags else None,
    ]
    thesis = " · ".join(t for t in thesis_bits if t)

    is_live = bool(snap.get("is_current_live"))
    if mds == "FALLBACK":
        tags = list(dict.fromkeys([*tags, "YAHOO_FALLBACK", "NOT_BROKER_LIVE"]))
    elif mds == "LIVE" and is_live:
        tags = list(dict.fromkeys([*tags, "KOTAK_LIVE"]))

    return {
        "symbol": symbol,
        "yahoo_symbol": snap.get("yahoo_symbol"),
        "side": side,
        "score": score,
        "thesis": thesis,
        "tags": tags,
        "price": price,
        "price_kind": "ltp",
        "feed_status": feed_status,
        "market_data_state": mds,
        "source": src,
        "quote_source": src,
        "provider_class": snap.get("provider_class"),
        "is_current_live": is_live,
        "is_last_observation": bool(snap.get("is_last_observation")),
        "timeframe": "5m",
        "strategy_id": INTRADAY_STRATEGY_ID,
        "strategy_version": INTRADAY_STRATEGY_VERSION,
        "data_interval": "5m",
        "quote_age_sec": age_sec,
        "quote_ts_iso": snap.get("quote_ts_iso"),
        "ingestion_ts_iso": snap.get("ingestion_ts_iso") or snap.get("as_of"),
        "change_pct": change,
        "prev_close": prev,
        "eod_anchor_prev_close": prev,
        "session_open": opens,
        "session_high": high,
        "session_low": low,
        "rsi_5m": rsi,
        "vwap": vwap,
        "stop": stop,
        "target": target,
        "currency": snap.get("currency") or "INR",
        "bars_5m": snap.get("bars_5m"),
        "disclaimer": "Intraday research bias only — not advice; scalp/risk yourself.",
    }


def build_intraday_desk(limit: int = 20) -> dict[str, Any]:
    session = session_snapshot()
    # Prefer names we already store EOD for (more liquid / known)
    try:
        from app.config import config
        from app.store import Database

        stored = {s.upper() for s in Database(config.db_path).get_all_symbols()}
    except Exception:  # noqa: BLE001
        stored = set()
    watch = [s for s in DEFAULT_WATCH if not stored or s in stored] or list(DEFAULT_WATCH)
    watch = watch[: max(5, min(30, int(limit)))]

    yahoo_map = {s: f"{s}.NS" for s in watch}
    snaps = live_quotes.fetch_many(list(yahoo_map.values()))
    quote_list = list(snaps.values())
    health = build_feed_health(quote_list, session=session)

    signals: list[dict[str, Any]] = []
    for sym, ysym in yahoo_map.items():
        snap = snaps.get(ysym)
        if not snap:
            signals.append(
                {
                    "symbol": sym,
                    "side": "FLAT",
                    "score": 0,
                    "thesis": "LIVE quote missing — no demo fallback",
                    "tags": ["NO_QUOTE", "FEED_ERROR"],
                    "price": None,
                    "price_kind": "ltp",
                    "feed_status": "ERROR",
                }
            )
            continue
        signals.append(_signal_for(sym, snap))

    if not health.live_calls_allowed:
        signals = freeze_live_sides(
            signals,
            health.message,
            market_data_state=str(health.market_data_state or health.feed_status),
        )

    # Phase 3: blend PCR / walls when an equity option chain is already active
    try:
        from app.kotak.option_chain import apply_chain_to_signal, get_option_chain_engine

        eng = get_option_chain_engine()
        for i, sig in enumerate(signals):
            sym = str(sig.get("symbol") or "").upper()
            # Map LONG/SHORT → BUY/SELL for shared chain rules
            side = str(sig.get("side") or "").upper()
            mapped = dict(sig)
            if side == "LONG":
                mapped["side"] = "BUY"
            elif side == "SHORT":
                mapped["side"] = "SELL"
            try:
                st = eng.status(sym)
                snap = eng.snapshot(sym) if st.get("active") else None
            except Exception:  # noqa: BLE001
                snap = None
            blended = apply_chain_to_signal(mapped, snap)
            if side in ("LONG", "SHORT", "FLAT"):
                # Restore intraday vocabulary
                bs = blended.get("side")
                if bs == "BUY":
                    blended["side"] = "LONG"
                elif bs == "SELL":
                    blended["side"] = "SHORT"
                elif bs == "HOLD":
                    blended["side"] = "FLAT"
            signals[i] = blended
    except Exception:  # noqa: BLE001
        pass

    signals.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    longs = [s for s in signals if s.get("side") == "LONG"]
    shorts = [s for s in signals if s.get("side") == "SHORT"]

    return {
        "desk": "intraday",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "feed_health": health.to_dict(),
        "live_calls_allowed": health.live_calls_allowed,
        "poll_seconds": 5,
        "count": len(signals),
        "long_count": len(longs),
        "short_count": len(shorts),
        "signals": signals,
        "top_longs": longs[:5],
        "top_shorts": shorts[:5],
        "message": health.message,
        "disclaimer": (
            "Educational research only. Intraday markets are noisy; "
            "no signal guarantees profit. Use hard stops and size risk 0.25–0.5% per idea. "
            "Prices are LTP (price_kind=ltp), not EOD closes. "
            "Yahoo age-fresh tape is FALLBACK (not Kotak broker LIVE)."
        ),
        "data_contract": {
            "price_kind": "ltp",
            "broker_live": health.broker_live,
            "market_data_state": health.market_data_state,
            "calendar_note": health.calendar_note,
        },
    }
