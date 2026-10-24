"""Deterministic DemoAdapter — 3 equities + 3 commodities for offline / CI."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Final

from app.adapters.base import (
    BarsPayload,
    FinancialsPayload,
    MarketDataAdapter,
    OiPayload,
    QuotePayload,
)

# Fixed as-of so payloads are bit-stable across runs (provenance always "demo").
_AS_OF: Final[str] = "2026-10-24T12:00:00+00:00"
_AS_OF_DT: Final[datetime] = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)

# Canonical MVP demo universe
EQUITIES: Final[tuple[str, ...]] = ("RELIANCE", "TCS", "INFY")
COMMODITIES: Final[tuple[str, ...]] = ("GOLD", "SILVER", "CRUDE")
DEMO_SYMBOLS: Final[frozenset[str]] = frozenset(EQUITIES + COMMODITIES)

# Seed quotes (INR for EQ; INR/oz or INR/bbl style marks for commodities)
_SEED: Final[dict[str, dict]] = {
    "RELIANCE": {
        "asset_class": "equity",
        "last": 2950.0,
        "currency": "INR",
        "pe": 28.5,
        "pb": 2.4,
        "market_cap": 1.99e13,
        "eps": 103.5,
        "dividend_yield": 0.35,
        "oi": 0.0,
    },
    "TCS": {
        "asset_class": "equity",
        "last": 4125.0,
        "currency": "INR",
        "pe": 32.1,
        "pb": 14.2,
        "market_cap": 1.50e13,
        "eps": 128.5,
        "dividend_yield": 1.2,
        "oi": 0.0,
    },
    "INFY": {
        "asset_class": "equity",
        "last": 1880.0,
        "currency": "INR",
        "pe": 26.8,
        "pb": 7.9,
        "market_cap": 7.8e12,
        "eps": 70.1,
        "dividend_yield": 2.1,
        "oi": 0.0,
    },
    "GOLD": {
        "asset_class": "commodity",
        "last": 72500.0,
        "currency": "INR",
        "pe": None,
        "pb": None,
        "market_cap": None,
        "eps": None,
        "dividend_yield": None,
        "oi": 185_000.0,
    },
    "SILVER": {
        "asset_class": "commodity",
        "last": 87500.0,
        "currency": "INR",
        "pe": None,
        "pb": None,
        "market_cap": None,
        "eps": None,
        "dividend_yield": None,
        "oi": 92_500.0,
    },
    "CRUDE": {
        "asset_class": "commodity",
        "last": 6450.0,
        "currency": "INR",
        "pe": None,
        "pb": None,
        "market_cap": None,
        "eps": None,
        "dividend_yield": None,
        "oi": 41_200.0,
    },
}


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def _unit_jitter(symbol: str, salt: str) -> float:
    """Deterministic [-1, 1] from symbol+salt (no RNG)."""
    digest = hashlib.sha256(f"{symbol}|{salt}".encode()).hexdigest()
    frac = int(digest[:8], 16) / 0xFFFFFFFF
    return frac * 2.0 - 1.0


def _close_series(symbol: str, n: int) -> list[float]:
    seed = _SEED[_norm(symbol)]["last"]
    closes: list[float] = []
    px = seed * (1.0 - 0.002 * n)
    for i in range(n):
        drift = 1.0 + 0.0015 * _unit_jitter(symbol, f"drift:{i}")
        px = round(px * drift, 2)
        closes.append(px)
    closes[-1] = float(seed)
    return closes


class DemoAdapter(MarketDataAdapter):
    """Offline market data for three NSE-style equities and three commodities."""

    @property
    def source_id(self) -> str:
        return "demo"

    def list_symbols(self) -> tuple[str, ...]:
        return EQUITIES + COMMODITIES

    def _require(self, symbol: str) -> str:
        sym = _norm(symbol)
        if sym not in _SEED:
            known = ", ".join(sorted(DEMO_SYMBOLS))
            raise KeyError(f"Unknown demo symbol {symbol!r}; known: {known}")
        return sym

    def get_quote(self, symbol: str) -> QuotePayload:
        sym = self._require(symbol)
        last = float(_SEED[sym]["last"])
        j = _unit_jitter(sym, "session")
        open_ = round(last * (1.0 - 0.004 * j), 2)
        high = round(max(open_, last) * (1.0 + 0.006 * abs(j)), 2)
        low = round(min(open_, last) * (1.0 - 0.005 * abs(j)), 2)
        prev = round(last * (1.0 - 0.003 * j), 2)
        change_pct = round(((last - prev) / prev) * 100.0, 4) if prev else 0.0
        volume = round(1_000_000 * (1.2 + _unit_jitter(sym, "vol")), 0)
        return QuotePayload(
            symbol=sym,
            last=last,
            open=open_,
            high=high,
            low=low,
            prev_close=prev,
            change_pct=change_pct,
            volume=float(volume),
            currency=str(_SEED[sym]["currency"]),
            provenance="demo",
            as_of=_AS_OF,
            source=self.source_id,
        )

    def get_bars(
        self,
        symbol: str,
        interval: str = "1d",
        lookback: int = 60,
    ) -> BarsPayload:
        sym = self._require(symbol)
        n = max(1, min(int(lookback), 260))
        closes = _close_series(sym, n)
        bars = []
        for i, close in enumerate(closes):
            j = _unit_jitter(sym, f"bar:{i}")
            open_ = round(close * (1.0 - 0.002 * j), 2)
            high = round(max(open_, close) * (1.0 + 0.004 * abs(j)), 2)
            low = round(min(open_, close) * (1.0 - 0.004 * abs(j)), 2)
            vol = round(800_000 * (1.0 + 0.3 * abs(j)), 0)
            if interval in ("1d", "d", "day"):
                trade_date = (_AS_OF_DT - timedelta(days=(n - 1 - i))).date().isoformat()
            else:
                ts = _AS_OF_DT - timedelta(hours=(n - 1 - i))
                trade_date = ts.isoformat()
            bars.append(
                {
                    "trade_date": trade_date,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": float(close),
                    "volume": float(vol),
                }
            )
        return BarsPayload(
            symbol=sym,
            interval=interval,
            bars=bars,
            provenance="demo",
            as_of=_AS_OF,
            source=self.source_id,
        )

    def get_oi(self, symbol: str) -> OiPayload:
        sym = self._require(symbol)
        base = float(_SEED[sym]["oi"])
        j = _unit_jitter(sym, "oi")
        change = round(base * 0.01 * j, 2) if base else 0.0
        pct = round((change / base) * 100.0, 4) if base else 0.0
        return OiPayload(
            symbol=sym,
            open_interest=base,
            oi_change=change,
            oi_change_pct=pct,
            provenance="demo",
            as_of=_AS_OF,
            source=self.source_id,
        )

    def get_financials(self, symbol: str) -> FinancialsPayload:
        sym = self._require(symbol)
        row = _SEED[sym]
        return FinancialsPayload(
            symbol=sym,
            pe=row["pe"],
            pb=row["pb"],
            market_cap=row["market_cap"],
            eps=row["eps"],
            dividend_yield=row["dividend_yield"],
            extras={
                "asset_class": row["asset_class"],
                "demo": True,
            },
            provenance="demo",
            as_of=_AS_OF,
            source=self.source_id,
        )
