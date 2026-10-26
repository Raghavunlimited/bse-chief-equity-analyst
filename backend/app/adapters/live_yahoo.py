"""
Live market-data adapter — Yahoo LTP + local Kotak/Yahoo EOD bars.

Refuses to invent prices. Missing symbols / failed fetches raise KeyError or
RuntimeError (callers must surface ERROR — never substitute demo).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import live_quotes
from app.adapters.base import (
    BarsPayload,
    FinancialsPayload,
    MarketDataAdapter,
    OiPayload,
    QuotePayload,
)
from app.config import config
from app.fundamentals import fetch_fundamentals
from app.store import Database


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _yahoo_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if s in ("NIFTY", "NIFTY50", "NIFTY 50"):
        return "^NSEI"
    if s in ("BANKNIFTY", "NIFTYBANK"):
        return "^NSEBANK"
    if s.startswith("^") or s.endswith(".NS"):
        return s
    return f"{s}.NS"


class LiveYahooAdapter(MarketDataAdapter):
    """Live adapter facade — resolves via Kotak WS then optional Yahoo FALLBACK."""

    @property
    def source_id(self) -> str:
        return "live_quote_provider"

    def get_quote(self, symbol: str) -> QuotePayload:
        ysym = _yahoo_symbol(symbol)
        q = live_quotes.quote_snapshot(ysym)
        qd = q.to_dict()
        if q.ltp is None or q.feed_status in ("ERROR", "UNAVAILABLE"):
            raise RuntimeError(
                f"LIVE quote unavailable for {symbol}: {q.error or q.feed_status}"
            )
        prev = float(q.prev_close or q.ltp)
        chg = float(q.change_pct or 0.0)
        # Use truthful provenance from LiveQuote (never map Yahoo → live)
        provenance = qd.get("provenance") or "delayed"
        return {
            "symbol": symbol.upper().strip(),
            "last": float(q.ltp),
            "open": float(q.session_open or q.ltp),
            "high": float(q.session_high or q.ltp),
            "low": float(q.session_low or q.ltp),
            "prev_close": prev,
            "change_pct": chg,
            "volume": float(q.session_volume or q.last_volume or 0.0),
            "currency": q.currency or "INR",
            "provenance": provenance,  # type: ignore[typeddict-item]
            "as_of": qd["as_of"],
            "source": q.source or self.source_id,
            "price_kind": "ltp",
            "feed_status": q.feed_status,
            "market_data_state": qd.get("market_data_state"),
            "quote_age_sec": q.age_sec,
            "is_current_live": qd.get("is_current_live"),
        }  # type: ignore[return-value]

    def get_bars(
        self,
        symbol: str,
        interval: str = "1d",
        lookback: int = 60,
    ) -> BarsPayload:
        if interval not in ("1d", "d", "day", "daily"):
            raise RuntimeError(
                f"LiveYahooAdapter Phase-1 only serves daily EOD bars; got interval={interval}"
            )
        db = Database(config.db_path)
        hist = db.get_symbol_history(symbol.upper().strip(), lookback=lookback)
        if hist is None or hist.empty:
            raise KeyError(f"No EOD bars in local store for {symbol} — run Force full / Refresh")
        bars = []
        for _, r in hist.iterrows():
            bars.append(
                {
                    "trade_date": str(r["trade_date"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": float(r["volume"]),
                    "price_kind": "eod_close",
                }
            )
        return {
            "symbol": symbol.upper().strip(),
            "interval": "1d",
            "bars": bars,  # type: ignore[typeddict-item]
            "provenance": "delayed",
            "as_of": _iso_now(),
            "source": "local_eod",
        }

    def get_oi(self, symbol: str) -> OiPayload:
        from app.signals.enrichment import _oi_from_option_chain

        block = _oi_from_option_chain(symbol.upper().strip())
        if not block.get("available"):
            raise RuntimeError(
                f"Open interest not available for {symbol} — "
                "activate Kotak option chain (no demo OI)"
            )
        oi = block.get("oi")
        oi_chg = block.get("oi_change")
        oi_pct = block.get("oi_pct_change")
        if oi is None:
            raise RuntimeError(f"Futures OI not yet streamed for {symbol}")
        return {
            "symbol": symbol.upper().strip(),
            "open_interest": float(oi),
            "oi_change": float(oi_chg or 0.0),
            "oi_change_pct": float(oi_pct or 0.0),
            "provenance": "live",
            "as_of": _iso_now(),
            "source": str(block.get("source") or "kotak_neo_ws"),
        }

    def get_financials(self, symbol: str) -> FinancialsPayload:
        f = fetch_fundamentals(symbol.upper().strip())
        if not f or not f.get("available"):
            raise KeyError(f"Financials unavailable for {symbol}")
        return {
            "symbol": symbol.upper().strip(),
            "pe": f.get("pe_ttm"),
            "pb": f.get("pb"),
            "market_cap": f.get("market_cap_cr"),
            "eps": f.get("eps_ttm"),
            "dividend_yield": f.get("dividend_yield_pct"),
            "extras": {k: f.get(k) for k in ("name", "source", "roe_pct", "recommendation")},
            "provenance": "delayed",
            "as_of": _iso_now(),
            "source": str(f.get("source") or "screener"),
        }

    def list_symbols(self) -> list[str]:
        db = Database(config.db_path)
        return list(db.get_all_symbols())
