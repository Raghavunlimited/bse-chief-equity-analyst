"""
Process-wide Kotak live feed hub.

Owns the WebSocket client, latest LiveQuote cache (with L2/OBI), prev-day OI,
and the 1m/5m/15m bar aggregator. Desks and API routes read from here.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config import config
from app.kotak.bars import BarAggregator
from app.kotak.depth import OrderBookSnapshot, build_order_book
from app.kotak.protocol import (
    FeedMessage,
    IndexTick,
    MarketPicture,
    MarketStatus,
    MiniTouch,
)
from app.kotak.scrip_master import Instrument, get_scrip_master
from app.kotak.session import KotakSession, SessionCredentials, get_kotak_session
from app.kotak.tick_guard import public_ws_status, should_accept_tick
from app.kotak.ws_client import KotakWebSocketClient, SubToken
from app.market_session import annotate_live_quote, assess_quote_age, session_snapshot
from app.market_types import LiveQuote

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class FeedHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._session = get_kotak_session()
        self._client: Optional[KotakWebSocketClient] = None
        self._quotes: dict[str, LiveQuote] = {}
        self._books: dict[str, OrderBookSnapshot] = {}
        self._prev_day_oi: dict[str, float] = {}
        self._session_oi_date: dict[str, str] = {}
        self._symbol_alias: dict[str, str] = {}  # NSE symbol / yahoo → key
        self._bars = BarAggregator()
        self._ws_state: dict[str, Any] = {"state": "idle"}
        self._ticks_dropped_ooo = 0
        self._ticks_accepted = 0

    # --- lifecycle -------------------------------------------------------

    def start(self, credentials: Optional[SessionCredentials] = None) -> dict[str, Any]:
        creds = credentials or self._session.require()
        with self._lock:
            if self._client and self._client.is_connected():
                return self.status()
            if self._client:
                self._client.stop()
            client = KotakWebSocketClient(
                creds,
                on_message=self._on_message,
                on_status=self._on_ws_status,
            )
            self._client = client
            client.start()
        ok = client.wait_connected(timeout=25.0)
        if not ok:
            raise RuntimeError(
                f"Kotak WebSocket failed to authenticate within 25s: {client.status()}"
            )
        return self.status()

    def stop(self) -> None:
        with self._lock:
            if self._client:
                self._client.stop()
                self._client = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            client_status = (
                public_ws_status(self._client.status())
                if self._client
                else {"connected": False, "authenticated": False}
            )
            from app.providers.live_quote_provider import provider_policy_public

            return {
                "session": self._session.status(),
                "ws": client_status,
                "quotes_cached": len(self._quotes),
                "books_cached": len(self._books),
                "ws_state": {
                    k: v
                    for k, v in dict(self._ws_state).items()
                    if k not in ("auth", "sid", "credentials")
                },
                "ticks_accepted": self._ticks_accepted,
                "ticks_dropped_out_of_order": self._ticks_dropped_ooo,
                "scrip_master": get_scrip_master().status(),
                "provider_policy": provider_policy_public(),
            }

    # --- subscribe -------------------------------------------------------

    def subscribe_instruments(
        self,
        instruments: list[Instrument | dict[str, str]],
        *,
        with_depth: bool = True,
        with_touch: bool = True,
    ) -> list[str]:
        """Subscribe tokens; returns feed keys ``segment|token``."""
        tokens: list[SubToken] = []
        keys: list[str] = []
        for inst in instruments:
            if isinstance(inst, Instrument):
                seg, tok, sym = inst.exchange_segment, inst.instrument_token, inst.symbol
            else:
                seg = str(inst["exchange_segment"])
                tok = str(inst["instrument_token"])
                sym = str(inst.get("symbol") or tok)
            tokens.append(SubToken(seg, tok))
            key = f"{seg}|{tok}"
            keys.append(key)
            with self._lock:
                self._symbol_alias[sym.upper()] = key
                self._symbol_alias[key] = key
        self._ensure_client()
        assert self._client is not None
        if with_depth:
            self._client.subscribe(tokens, intent="depth")
        if with_touch:
            self._client.subscribe(tokens, intent="scrips")
        return keys

    def subscribe_equity(self, symbol: str, *, exchange_segment: str = "nse_cm") -> str:
        inst = get_scrip_master().resolve_equity(symbol, exchange_segment=exchange_segment)
        return self.subscribe_instruments([inst])[0]

    def subscribe_future(
        self,
        underlying: str,
        expiry: str | None = None,
        *,
        exchange_segment: str = "nse_fo",
    ) -> str:
        sm = get_scrip_master()
        if expiry:
            inst = sm.resolve_future(underlying, expiry, exchange_segment=exchange_segment)
        else:
            inst = sm.nearest_future(underlying, exchange_segment=exchange_segment)
        return self.subscribe_instruments([inst])[0]

    def subscribe_option(
        self,
        underlying: str,
        expiry: str,
        strike: float,
        right: str,
        *,
        exchange_segment: str = "nse_fo",
    ) -> str:
        inst = get_scrip_master().resolve_option(
            underlying, expiry, strike, right, exchange_segment=exchange_segment
        )
        return self.subscribe_instruments([inst])[0]

    def unsubscribe(self, keys: list[str], *, intent: str = "depth") -> None:
        toks = []
        for key in keys:
            if "|" not in key:
                continue
            seg, tok = key.split("|", 1)
            toks.append(SubToken(seg, tok))
        if self._client and toks:
            self._client.unsubscribe(toks, intent=intent)
            if intent == "depth":
                self._client.unsubscribe(toks, intent="scrips")

    # --- reads -----------------------------------------------------------

    def get_quote(self, key_or_symbol: str) -> Optional[LiveQuote]:
        with self._lock:
            key = self._symbol_alias.get(key_or_symbol.upper(), key_or_symbol)
            return self._quotes.get(key)

    def get_book(self, key_or_symbol: str) -> Optional[OrderBookSnapshot]:
        with self._lock:
            key = self._symbol_alias.get(key_or_symbol.upper(), key_or_symbol)
            return self._books.get(key)

    def get_bars(
        self, key_or_symbol: str, interval: str = "1m", *, limit: int = 200
    ) -> list[dict[str, Any]]:
        with self._lock:
            key = self._symbol_alias.get(key_or_symbol.upper(), key_or_symbol)
        if interval not in ("1m", "5m", "15m"):
            raise ValueError("interval must be 1m, 5m, or 15m")
        return self._bars.bars_with_current(key, interval, limit=limit)  # type: ignore[arg-type]

    def quote_for_yahoo_symbol(self, yahoo_symbol: str) -> Optional[LiveQuote]:
        """Map Yahoo-style symbols (RELIANCE.NS, ^NSEI) onto Kotak cache if present."""
        raw = yahoo_symbol.upper().strip()
        if raw in ("^NSEI", "NSEI", "NIFTY", "NIFTY 50"):
            candidates = ("NIFTY", "NIFTY 50", "nse_cm|Nifty 50")
        elif raw in ("^NSEBANK", "BANKNIFTY", "NIFTY BANK"):
            candidates = ("BANKNIFTY", "NIFTY BANK", "nse_cm|Nifty Bank")
        else:
            base = raw.replace(".NS", "").replace(".BO", "")
            candidates = (base, f"{base}-EQ")
        for c in candidates:
            q = self.get_quote(c)
            if q and q.ltp is not None:
                return q
        return None

    # --- internals -------------------------------------------------------

    def _ensure_client(self) -> None:
        with self._lock:
            if self._client and self._client.is_connected():
                return
        self.start()

    def _on_ws_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            safe = {
                k: v
                for k, v in dict(payload).items()
                if k not in ("auth", "sid", "credentials", "mpin")
            }
            if safe.get("last_error"):
                from app.kotak.tick_guard import sanitize_error_text

                safe["last_error"] = sanitize_error_text(safe["last_error"])
            self._ws_state = safe

    def _on_message(self, msg: FeedMessage) -> None:
        if isinstance(msg, MarketStatus):
            return
        if isinstance(msg, MarketPicture):
            self._ingest_picture(msg)
        elif isinstance(msg, MiniTouch):
            self._ingest_mini(msg)
        elif isinstance(msg, IndexTick):
            self._ingest_index(msg)

    def _commit_quote(
        self,
        key: str,
        quote: LiveQuote,
        *,
        book: OrderBookSnapshot | None = None,
        aliases: list[str] | None = None,
    ) -> bool:
        with self._lock:
            prev = self._quotes.get(key)
            prev_ts = prev.quote_ts_unix if prev else None
            ok, reason = should_accept_tick(
                incoming_ts=quote.quote_ts_unix,
                previous_ts=prev_ts,
                incoming_ltp=quote.ltp,
            )
            if not ok:
                if reason == "out_of_order":
                    self._ticks_dropped_ooo += 1
                return False
            annotated = annotate_live_quote(quote)
            self._quotes[key] = annotated
            self._ticks_accepted += 1
            if book is not None:
                self._books[key] = book
            for a in aliases or []:
                if a:
                    self._symbol_alias[str(a).upper()] = key
            return True

    def _ingest_picture(self, msg: MarketPicture) -> None:
        key = f"{msg.exchange_segment}|{msg.instrument_token}"
        book = build_order_book(msg.buy, msg.sell, max_levels=5)
        prev_oi = self._track_prev_oi(key, float(msg.open_interest), msg.last_trade_time)
        now = time.time()
        ts = float(msg.last_trade_time or msg.last_update_time or now)
        sess = session_snapshot()
        status, age, _ = assess_quote_age(ts, now_unix=now, session=sess)
        change_pct = msg.net_change_percent
        if change_pct is None and msg.close_price:
            change_pct = ((msg.last_traded_price - msg.close_price) / msg.close_price) * 100.0
        symbol = (msg.trading_symbol or msg.instrument_token or "").replace("-EQ", "")
        quote = LiveQuote(
            symbol=symbol,
            ltp=msg.last_traded_price,
            quote_ts_unix=ts,
            fetched_at_unix=now,
            age_sec=age,
            feed_status=status,
            source="kotak_neo_ws",
            timeframe="ltp",
            prev_close=msg.close_price or None,
            change_pct=change_pct,
            session_open=msg.open_price or None,
            session_high=msg.high_price or None,
            session_low=msg.low_price or None,
            last_volume=float(msg.last_trade_qty) if msg.last_trade_qty else None,
            session_volume=float(msg.volume_traded_today) if msg.volume_traded_today else None,
            vwap=msg.average_trade_price or None,
            exchange=msg.exchange_segment,
            instrument_token=msg.instrument_token,
            exchange_segment=msg.exchange_segment,
            ltq=float(msg.last_trade_qty) if msg.last_trade_qty else None,
            atp=msg.average_trade_price or None,
            oi=float(msg.open_interest) if msg.open_interest else None,
            prev_day_oi=prev_oi,
            depth_bids=tuple(
                {"price": b.price, "quantity": b.quantity, "orders": b.orders} for b in book.bids
            ),
            depth_asks=tuple(
                {"price": a.price, "quantity": a.quantity, "orders": a.orders} for a in book.asks
            ),
            obi=book.obi,
            spread_pct=book.spread_pct,
            exchange_timestamp=int(ts),
        )
        aliases = [symbol]
        if msg.trading_symbol:
            aliases.append(msg.trading_symbol)
            aliases.append(msg.trading_symbol.replace("-EQ", ""))
        if not self._commit_quote(key, quote, book=book, aliases=aliases):
            return
        closed = self._bars.on_tick(
            key=key,
            price=msg.last_traded_price,
            ts_unix=ts,
            session_volume=float(msg.volume_traded_today or 0),
            oi=float(msg.open_interest or 0),
        )
        self._persist_closed_5m(symbol, closed)

    def _ingest_mini(self, msg: MiniTouch) -> None:
        key = f"{msg.exchange_segment}|{msg.instrument_token}"
        now = time.time()
        ts = float(msg.last_trade_time or now)
        with self._lock:
            prev = self._quotes.get(key)
            book = self._books.get(key)
        sess = session_snapshot()
        status, age, _ = assess_quote_age(ts, now_unix=now, session=sess)
        symbol = (msg.trading_symbol or (prev.symbol if prev else msg.instrument_token) or "").replace(
            "-EQ", ""
        )
        quote = LiveQuote(
            symbol=symbol,
            ltp=msg.last_traded_price,
            quote_ts_unix=ts,
            fetched_at_unix=now,
            age_sec=age,
            feed_status=status,
            source="kotak_neo_ws",
            timeframe="ltp",
            prev_close=msg.close_price or (prev.prev_close if prev else None),
            change_pct=msg.net_change_percent,
            session_open=prev.session_open if prev else None,
            session_high=prev.session_high if prev else None,
            session_low=prev.session_low if prev else None,
            last_volume=float(msg.last_trade_qty) if msg.last_trade_qty else None,
            session_volume=prev.session_volume if prev else None,
            vwap=prev.vwap if prev else None,
            exchange=msg.exchange_segment,
            instrument_token=msg.instrument_token,
            exchange_segment=msg.exchange_segment,
            ltq=float(msg.last_trade_qty) if msg.last_trade_qty else None,
            atp=prev.atp if prev else None,
            oi=prev.oi if prev else None,
            prev_day_oi=prev.prev_day_oi if prev else None,
            depth_bids=prev.depth_bids if prev else (),
            depth_asks=prev.depth_asks if prev else (),
            obi=book.obi if book else (prev.obi if prev else None),
            spread_pct=book.spread_pct if book else (prev.spread_pct if prev else None),
            exchange_timestamp=int(ts),
        )
        aliases = [symbol]
        if msg.trading_symbol:
            aliases.append(msg.trading_symbol.replace("-EQ", ""))
        if not self._commit_quote(key, quote, aliases=aliases):
            return
        closed = self._bars.on_tick(
            key=key,
            price=msg.last_traded_price,
            ts_unix=ts,
            session_volume=float(quote.session_volume or 0),
            oi=float(quote.oi or 0),
        )
        self._persist_closed_5m(symbol, closed)

    def _ingest_index(self, msg: IndexTick) -> None:
        key = f"{msg.exchange_segment}|{msg.instrument_token}"
        now = time.time()
        ts = float(msg.last_trade_time or now)
        sess = session_snapshot()
        status, age, _ = assess_quote_age(ts, now_unix=now, session=sess)
        name = msg.name or msg.trading_symbol or msg.instrument_token
        quote = LiveQuote(
            symbol=name,
            ltp=msg.last_traded_price,
            quote_ts_unix=ts,
            fetched_at_unix=now,
            age_sec=age,
            feed_status=status,
            source="kotak_neo_ws",
            timeframe="ltp",
            prev_close=msg.close_price or None,
            change_pct=msg.net_change_percent,
            session_open=msg.open_price or None,
            session_high=msg.high_price or None,
            session_low=msg.low_price or None,
            exchange=msg.exchange_segment,
            instrument_token=msg.instrument_token,
            exchange_segment=msg.exchange_segment,
            exchange_timestamp=int(ts),
        )
        aliases = [name]
        if "NIFTY" in name.upper() and "BANK" not in name.upper():
            aliases.append("NIFTY")
        if "BANK" in name.upper():
            aliases.append("BANKNIFTY")
        if not self._commit_quote(key, quote, aliases=aliases):
            return
        closed = self._bars.on_tick(
            key=key, price=msg.last_traded_price, ts_unix=ts, session_volume=0, oi=0
        )
        persist_sym = "NIFTY" if "NIFTY" in name.upper() and "BANK" not in name.upper() else name
        if "BANK" in name.upper():
            persist_sym = "BANKNIFTY"
        self._persist_closed_5m(persist_sym, closed)

    def _persist_closed_5m(self, symbol: str, closed: list) -> None:
        """Best-effort SQLite persist of completed 5m buckets (Phase 3)."""
        if not closed or not symbol:
            return
        try:
            from app.bars_5m import persist_kotak_closed_bar

            for bar in closed:
                if getattr(bar, "interval", None) != "5m":
                    continue
                if not getattr(bar, "closed", False):
                    continue
                persist_kotak_closed_bar(
                    symbol=str(symbol).replace("-EQ", ""),
                    bar_start_unix=int(bar.bucket_start_unix),
                    open_=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume or 0.0),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("bars_5m kotak persist skipped: %s", exc)

    def _track_prev_oi(self, key: str, oi: float, ts_unix: float) -> Optional[float]:
        if oi <= 0:
            with self._lock:
                return self._prev_day_oi.get(key)
        day = datetime.fromtimestamp(ts_unix or time.time(), tz=IST).date().isoformat()
        with self._lock:
            prev_day = self._session_oi_date.get(key)
            if prev_day is None:
                self._session_oi_date[key] = day
                # First observation of process — no prior day yet.
                return self._prev_day_oi.get(key)
            if day != prev_day:
                # New session: freeze last OI of previous day.
                last = self._quotes.get(key)
                if last and last.oi:
                    self._prev_day_oi[key] = float(last.oi)
                self._session_oi_date[key] = day
            return self._prev_day_oi.get(key)


_hub: Optional[FeedHub] = None
_hub_lock = threading.Lock()


def get_feed_hub() -> FeedHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = FeedHub()
        return _hub
