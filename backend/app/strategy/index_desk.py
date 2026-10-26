"""
Index desk — NIFTY 50 + BANK NIFTY directional research bias.

No "holy grail". Combines the stack used by most liquid index desks:
  1) Daily regime filter (close vs SMA20 / SMA50)
  2) Intraday structure (EMA9 / EMA21 on 5m, slope)
  3) VWAP reclaim / reject when session volume exists
  4) RSI(14) dampener on 5m
  5) ATR-proxy stops from session range
  6) Relative strength BankNifty vs Nifty (spread day-change)

Research only — not investment advice. Phase 3 wires live PCR / walls when Kotak chain is active.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import live_quotes
from app.config import config
from app.market_session import build_feed_health, freeze_live_sides, session_snapshot
from app.market_types import LiveQuote
from app.store import Database
from app.strategy.index_core import (
    STRATEGY_ID as INDEX_STRATEGY_ID,
    STRATEGY_VERSION as INDEX_STRATEGY_VERSION,
    ema as _ema,
    rsi as _rsi,
    score_index_mtf,
    slope_pct as _slope_pct,
)
from app.strategy.weekly_swing import check_market_regime

INDEX_SPECS = (
    {
        "symbol": "NIFTY",
        "yahoo": "^NSEI",
        "label": "Nifty 50",
        "lot_hint": "Nifty futures / options (NSE)",
    },
    {
        "symbol": "BANKNIFTY",
        "yahoo": "^NSEBANK",
        "label": "Bank Nifty",
        "lot_hint": "BankNifty futures / options (NSE)",
    },
)

STRATEGY_NAME = INDEX_STRATEGY_ID
STRATEGY_NOTES = (
    "Multi-timeframe trend + VWAP + RSI. Daily SMA regime gates aggression; "
    "5m EMA stack and VWAP set the active bias. Relative BN–Nifty spread "
    "tilts BankNifty confidence. When Kotak option chain is live, OI-PCR "
    "regime + Call/Put wall proximity adjust confidence. Not a guaranteed edge. "
    f"Shared core {INDEX_STRATEGY_VERSION} with 5m expectancy (no daily proxy gate)."
)


def _daily_from_db(symbol: str) -> dict[str, Any]:
    """Pull stored EOD for NIFTY; BankNifty may be absent until Yahoo fill."""
    db = Database(config.db_path)
    if symbol == "NIFTY":
        series = db.get_nifty_series(lookback=80)
        regime = check_market_regime(series)
        last = None
        if series is not None and not series.empty:
            last = float(series.iloc[-1]["close"])
            as_of = str(series.iloc[-1]["trade_date"])
        else:
            as_of = None
        return {
            "eod_close": last,
            "eod_as_of": as_of,
            "regime": regime.get("regime"),
            "allow_trading": bool(regime.get("allow_trading")),
            "regime_reason": regime.get("reason"),
            "sma_20": regime.get("nifty_sma_20"),
            "sma_50": regime.get("nifty_sma_50"),
            "change_20d": regime.get("nifty_change_20d"),
        }
    # BANKNIFTY — optional local series if ever ingested under that symbol
    hist = db.get_symbol_history("BANKNIFTY", lookback=80)
    if hist is None or hist.empty:
        return {
            "eod_close": None,
            "eod_as_of": None,
            "regime": None,
            "allow_trading": None,
            "regime_reason": "No local BANKNIFTY EOD — using live tape only",
            "sma_20": None,
            "sma_50": None,
            "change_20d": None,
        }
    close = hist["close"].astype(float)
    price = float(close.iloc[-1])
    sma_20 = float(close.tail(20).mean()) if len(close) >= 20 else None
    sma_50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    chg_20 = None
    if len(close) >= 20 and float(close.iloc[-20]):
        chg_20 = (price / float(close.iloc[-20]) - 1.0) * 100.0
    if sma_20 and sma_50 and price > sma_20 > sma_50:
        regime, allow, reason = "BULL", True, "BANKNIFTY above SMA20 > SMA50"
    elif sma_50 and price < sma_50:
        regime, allow, reason = "BEAR", False, "BANKNIFTY below SMA50"
    else:
        regime, allow, reason = "NEUTRAL", False, "BANKNIFTY mixed vs SMAs"
    return {
        "eod_close": price,
        "eod_as_of": str(hist.iloc[-1]["trade_date"]),
        "regime": regime,
        "allow_trading": allow,
        "regime_reason": reason,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "change_20d": chg_20,
    }


def _score_index(
    *,
    symbol: str,
    snap: dict[str, Any] | LiveQuote,
    daily: dict[str, Any],
    rel_spread: float | None,
) -> dict[str, Any]:
    if isinstance(snap, LiveQuote):
        snap = snap.to_dict()
    price = snap.get("price") or snap.get("ltp")
    feed_status = snap.get("feed_status")
    if price is None or feed_status == "ERROR":
        return {
            "symbol": symbol,
            "side": "HOLD",
            "score": 0.0,
            "confidence": 0.0,
            "thesis": f"{symbol}: LIVE quote ERROR — {snap.get('error') or 'no LTP'} (no demo)",
            "tags": ["NO_QUOTE", "FEED_ERROR"],
            "price": None,
            "price_kind": "ltp",
            "feed_status": "ERROR",
        }

    closes = list(snap.get("closes_5m") or [])
    vwap = snap.get("vwap")
    day_chg = snap.get("change_pct")
    sess_hi = snap.get("session_high")
    sess_lo = snap.get("session_low")
    prev = snap.get("prev_close")

    core = score_index_mtf(
        symbol=symbol,
        price=float(price),
        closes_5m=closes,
        daily_regime=daily.get("regime"),
        vwap=float(vwap) if vwap is not None else None,
        change_pct=float(day_chg) if day_chg is not None else None,
        session_high=float(sess_hi) if sess_hi is not None else None,
        session_low=float(sess_lo) if sess_lo is not None else None,
        rel_spread=rel_spread,
    )
    side = core["side"]
    score = core["score"]
    tags = list(core["tags"])
    bits = list(core["bits"])
    conf = core["confidence"]
    rsi = core["rsi_5m"]
    stop = core["stop"]
    target = core["target"]
    ema9 = core["ema9"]
    ema21 = core["ema21"]
    slope = core["slope_pct"]

    thesis = (
        f"{symbol}: {side} bias · score {score:.0f} @ {price:.2f}"
        + (f" · day {day_chg:+.2f}%" if day_chg is not None else "")
        + (f" · RSI {rsi:.0f}" if rsi is not None else "")
        + (f" · {'; '.join(bits)}" if bits else "")
    )

    mds = snap.get("market_data_state") or feed_status
    src = snap.get("source")
    if mds == "FALLBACK":
        tags = list(dict.fromkeys([*tags, "YAHOO_FALLBACK", "NOT_BROKER_LIVE"]))
    elif mds == "LIVE" and snap.get("is_current_live"):
        tags = list(dict.fromkeys([*tags, "KOTAK_LIVE"]))

    return {
        "symbol": symbol,
        "side": side,
        "score": round(score, 1),
        "confidence": conf,
        "thesis": thesis,
        "strategy_id": INDEX_STRATEGY_ID,
        "strategy_version": INDEX_STRATEGY_VERSION,
        "data_interval": "5m",
        "tags": tags,
        "price": float(price),
        "price_kind": "ltp",
        "feed_status": feed_status,
        "market_data_state": mds,
        "source": src,
        "quote_source": src,
        "provider_class": snap.get("provider_class"),
        "is_current_live": bool(snap.get("is_current_live")),
        "is_last_observation": bool(snap.get("is_last_observation")),
        "timeframe": snap.get("timeframe") or "5m",
        "quote_age_sec": snap.get("age_sec"),
        "quote_ts_iso": snap.get("quote_ts_iso"),
        "ingestion_ts_iso": snap.get("ingestion_ts_iso") or snap.get("as_of"),
        "prev_close": float(prev) if prev is not None else None,
        "eod_anchor": {
            "price_kind": "eod_close",
            "close": daily.get("eod_close"),
            "as_of": daily.get("eod_as_of"),
            "sma_20": daily.get("sma_20"),
            "sma_50": daily.get("sma_50"),
            "regime": daily.get("regime"),
        },
        "change_pct": day_chg,
        "vwap": vwap,
        "ema9": round(ema9, 2) if ema9 is not None else None,
        "ema21": round(ema21, 2) if ema21 is not None else None,
        "rsi_5m": rsi,
        "slope_6": round(slope, 3) if slope is not None else None,
        "session_high": sess_hi,
        "session_low": sess_lo,
        "stop": stop,
        "target": target,
        "daily": daily,
        "rel_vs_nifty_pct": rel_spread if symbol == "BANKNIFTY" else None,
    }


def build_index_desk() -> dict[str, Any]:
    session = session_snapshot()
    yahoos = [s["yahoo"] for s in INDEX_SPECS]
    snaps = live_quotes.fetch_many(yahoos, max_workers=4)
    health = build_feed_health(list(snaps.values()), session=session)

    nifty_snap = snaps.get("^NSEI")
    bn_snap = snaps.get("^NSEBANK")
    n_chg = nifty_snap.change_pct if nifty_snap else None
    b_chg = bn_snap.change_pct if bn_snap else None
    rel = None
    if n_chg is not None and b_chg is not None:
        rel = round(float(b_chg) - float(n_chg), 3)

    signals: list[dict[str, Any]] = []
    for spec in INDEX_SPECS:
        snap = snaps.get(spec["yahoo"])
        if snap is None:
            signals.append(
                {
                    "symbol": spec["symbol"],
                    "side": "HOLD",
                    "score": 0.0,
                    "confidence": 0.0,
                    "thesis": f"{spec['symbol']}: LIVE quote missing — no demo fallback",
                    "tags": ["NO_QUOTE", "FEED_ERROR"],
                    "price": None,
                    "price_kind": "ltp",
                    "feed_status": "ERROR",
                    "label": spec["label"],
                    "yahoo": spec["yahoo"],
                    "lot_hint": spec["lot_hint"],
                }
            )
            continue
        daily = _daily_from_db(spec["symbol"])
        # For BankNifty without local EOD, inherit Nifty daily regime as soft gate
        if spec["symbol"] == "BANKNIFTY" and daily.get("regime") is None:
            n_daily = _daily_from_db("NIFTY")
            daily = {
                **daily,
                "regime": n_daily.get("regime"),
                "allow_trading": n_daily.get("allow_trading"),
                "regime_reason": (
                    f"Using NIFTY regime proxy — {n_daily.get('regime_reason')}"
                ),
                "sma_20": n_daily.get("sma_20"),
                "sma_50": n_daily.get("sma_50"),
            }
        sig = _score_index(
            symbol=spec["symbol"],
            snap=snap,
            daily=daily,
            rel_spread=rel if spec["symbol"] == "BANKNIFTY" else None,
        )
        sig["label"] = spec["label"]
        sig["yahoo"] = spec["yahoo"]
        sig["lot_hint"] = spec["lot_hint"]
        signals.append(sig)

    if not health.live_calls_allowed:
        signals = freeze_live_sides(
            signals,
            health.message,
            market_data_state=str(health.market_data_state or health.feed_status),
        )

    chain_by_sym = _attach_option_chains(signals)

    buys = sum(1 for s in signals if s["side"] == "BUY")
    sells = sum(1 for s in signals if s["side"] == "SELL")
    holds = sum(1 for s in signals if s["side"] == "HOLD")

    return {
        "desk": "index",
        "horizon": "intraday+daily",
        "strategy": STRATEGY_NAME,
        "strategy_notes": STRATEGY_NOTES,
        "session": session,
        "feed_health": health.to_dict(),
        "live_calls_allowed": health.live_calls_allowed,
        "poll_seconds": 5,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "relative_bn_vs_nifty_pct": rel,
        "signals": signals,
        "option_chains": chain_by_sym,
        "buy_count": buys,
        "sell_count": sells,
        "hold_count": holds,
        "message": health.message,
        "disclaimer": (
            "Research bias only. Index F&O is leveraged. "
            "LTP (price_kind=ltp) is distinct from EOD anchors (price_kind=eod_close). "
            "Yahoo age-fresh tape is FALLBACK (not Kotak broker LIVE). "
            "Option-chain PCR / walls require a live Kotak session. "
            "Not investment advice; no guaranteed edge."
        ),
        "data_contract": {
            "price_kind": "ltp",
            "broker_live": health.broker_live,
            "market_data_state": health.market_data_state,
            "calendar_note": health.calendar_note,
        },
    }


def _attach_option_chains(signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Blend live chain analytics into each index signal when chain is active."""
    out: dict[str, Any] = {}
    try:
        from app.kotak.option_chain import apply_chain_to_signal, get_option_chain_engine

        eng = get_option_chain_engine()
    except Exception as e:  # noqa: BLE001
        for i, sig in enumerate(signals):
            signals[i] = {
                **sig,
                "option_chain": {"available": False, "reason": str(e)},
            }
        return out

    for i, sig in enumerate(signals):
        sym = str(sig.get("symbol") or "").upper()
        snap = None
        try:
            st = eng.status(sym)
            if st.get("active"):
                snap = eng.snapshot(sym)
                out[sym] = {
                    "expiry": snap.get("expiry"),
                    "analytics": snap.get("analytics"),
                    "atm": snap.get("atm"),
                    "spot": snap.get("spot"),
                    "future_buildup": (snap.get("future") or {}).get("buildup"),
                }
        except Exception as e:  # noqa: BLE001
            signals[i] = {
                **sig,
                "option_chain": {"available": False, "reason": str(e)},
            }
            continue
        signals[i] = apply_chain_to_signal(sig, snap)
    return out
