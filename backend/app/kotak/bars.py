"""
Live intraday bar aggregator — 1m / 5m / 15m OHLCV + OI from WebSocket ticks.

Volume on each closed bar is the session-volume delta within that bucket.
OI is the last open-interest observed in the bucket (F&O); 0 for cash.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BarInterval = Literal["1m", "5m", "15m"]
_INTERVAL_SEC: dict[BarInterval, int] = {"1m": 60, "5m": 300, "15m": 900}


@dataclass
class IntradayBar:
    interval: BarInterval
    bucket_start_unix: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    oi: float
    ticks: int = 0
    closed: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bucket_start_iso"] = datetime.fromtimestamp(
            self.bucket_start_unix, tz=timezone.utc
        ).isoformat()
        d["bucket_start_ist"] = datetime.fromtimestamp(
            self.bucket_start_unix, tz=IST
        ).isoformat()
        return d


@dataclass
class _OpenBucket:
    interval: BarInterval
    start: int
    open: float
    high: float
    low: float
    close: float
    oi: float
    volume_start: float
    volume_end: float
    ticks: int = 0


class BarAggregator:
    """Per-instrument multi-timeframe OHLCV+OI aggregator (thread-safe)."""

    def __init__(self, *, max_closed_bars: int = 780) -> None:
        self.max_closed_bars = max_closed_bars
        self._lock = threading.RLock()
        # key = "segment|token" → interval → open bucket
        self._open: dict[str, dict[BarInterval, _OpenBucket]] = {}
        # key → interval → closed bars (oldest → newest)
        self._closed: dict[str, dict[BarInterval, list[IntradayBar]]] = {}

    def on_tick(
        self,
        *,
        key: str,
        price: float,
        ts_unix: float,
        session_volume: float | None = None,
        oi: float | None = None,
    ) -> list[IntradayBar]:
        """Ingest one tick; returns any bars that just closed."""
        if price is None or price <= 0 or ts_unix <= 0:
            return []
        closed_out: list[IntradayBar] = []
        vol = float(session_volume) if session_volume is not None else 0.0
        oi_v = float(oi) if oi is not None else 0.0
        with self._lock:
            for interval, sec in _INTERVAL_SEC.items():
                bucket = int(ts_unix) // sec * sec
                by_iv = self._open.setdefault(key, {})
                cur = by_iv.get(interval)
                if cur is None:
                    by_iv[interval] = _OpenBucket(
                        interval=interval,
                        start=bucket,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        oi=oi_v,
                        volume_start=vol,
                        volume_end=vol,
                        ticks=1,
                    )
                    continue
                if bucket > cur.start:
                    closed_out.append(self._close(key, cur))
                    by_iv[interval] = _OpenBucket(
                        interval=interval,
                        start=bucket,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        oi=oi_v,
                        volume_start=vol,
                        volume_end=vol,
                        ticks=1,
                    )
                elif bucket == cur.start:
                    cur.high = max(cur.high, price)
                    cur.low = min(cur.low, price)
                    cur.close = price
                    cur.oi = oi_v
                    cur.volume_end = vol
                    cur.ticks += 1
                # else: out-of-order older tick — ignore for OHLCV integrity
        return closed_out

    def _close(self, key: str, cur: _OpenBucket) -> IntradayBar:
        bar = IntradayBar(
            interval=cur.interval,
            bucket_start_unix=cur.start,
            open=cur.open,
            high=cur.high,
            low=cur.low,
            close=cur.close,
            volume=max(0.0, cur.volume_end - cur.volume_start),
            oi=cur.oi,
            ticks=cur.ticks,
            closed=True,
        )
        store = self._closed.setdefault(key, {}).setdefault(cur.interval, [])
        store.append(bar)
        if len(store) > self.max_closed_bars:
            del store[: len(store) - self.max_closed_bars]
        return bar

    def current_bar(self, key: str, interval: BarInterval) -> Optional[IntradayBar]:
        with self._lock:
            cur = self._open.get(key, {}).get(interval)
            if cur is None:
                return None
            return IntradayBar(
                interval=cur.interval,
                bucket_start_unix=cur.start,
                open=cur.open,
                high=cur.high,
                low=cur.low,
                close=cur.close,
                volume=max(0.0, cur.volume_end - cur.volume_start),
                oi=cur.oi,
                ticks=cur.ticks,
                closed=False,
            )

    def closed_bars(
        self, key: str, interval: BarInterval, *, limit: int = 200
    ) -> list[IntradayBar]:
        with self._lock:
            rows = list(self._closed.get(key, {}).get(interval, []))
        if limit > 0:
            rows = rows[-limit:]
        return rows

    def bars_with_current(
        self, key: str, interval: BarInterval, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        closed = self.closed_bars(key, interval, limit=max(0, limit - 1))
        out = [b.to_dict() for b in closed]
        cur = self.current_bar(key, interval)
        if cur is not None:
            out.append(cur.to_dict())
        if limit > 0:
            out = out[-limit:]
        return out

    def snapshot(self, key: str) -> dict[str, Any]:
        return {
            interval: self.bars_with_current(key, interval)
            for interval in _INTERVAL_SEC
        }
