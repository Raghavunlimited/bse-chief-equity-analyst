"""
Kotak Neo market-data WebSocket client (HS / apifeed ``native_batch``).

Verified against Kotak's Market Data WebSocket Developer Guide (feedUrl → wss
…/apifeed, JSON auth then little-endian native_batch). Kotak announced a new
SFeed protocol with a migration deadline of 15 Sep 2026 — this client has NOT
been rewritten for SFeed; do not treat URL-only changes as a migration.

Connects with live session credentials, authenticates, supports dynamic
subscribe/unsubscribe, exponential-backoff reconnect, and WebSocket ping/pong.
Auth failures are fatal (no credential-spam reconnect).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from app.kotak.tick_guard import sanitize_error_text
from app.kotak.protocol import (
    EXCHANGE_NAME_TO_ID,
    MSG_AUTH_FAIL,
    MSG_AUTH_RESPONSE_CODES,
    MSG_SUBSCRIBE_ACK,
    FeedMessage,
    IndexTick,
    MarketPicture,
    MarketStatus,
    MiniTouch,
    decode_packet,
    split_batch,
)
from app.kotak.session import SessionCredentials

logger = logging.getLogger(__name__)

MessageHandler = Callable[[FeedMessage], None]
StatusHandler = Callable[[dict[str, Any]], None]

_SUBSCRIBE_EVENTS = {
    "scrips": "subscribeScrips",
    "scrips_lite": "subscribeScripsLite",
    "depth": "subscribeDepth",
    "index": "subscribeIndices",
}
_UNSUBSCRIBE_EVENTS = {
    "scrips": "unsubscribeScrips",
    "scrips_lite": "unsubscribeScripsLite",
    "depth": "unsubscribeDepth",
    "index": "unsubscribeIndices",
}


@dataclass(frozen=True)
class SubToken:
    exchange_segment: str
    instrument_token: str

    @property
    def inputtoken(self) -> str:
        return f"{self.exchange_segment}|{self.instrument_token}"


class KotakWebSocketClient:
    """
    Background-thread asyncio WebSocket client.

    Call ``start()`` after constructing; use ``subscribe`` / ``unsubscribe``
    from any thread. Messages are delivered on the asyncio thread via
    ``on_message`` — keep handlers fast / non-blocking.
    """

    def __init__(
        self,
        credentials: SessionCredentials,
        *,
        on_message: Optional[MessageHandler] = None,
        on_status: Optional[StatusHandler] = None,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        max_backoff_sec: float = 60.0,
        max_subscriptions: int = 3000,
    ) -> None:
        self.credentials = credentials
        self.on_message = on_message
        self.on_status = on_status
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.max_backoff_sec = max_backoff_sec
        self.max_subscriptions = max_subscriptions

        self._dividers: dict[int, int] = {i: 100 for i in EXCHANGE_NAME_TO_ID.values()}
        self._subscriptions: set[tuple[str, str, str]] = set()  # (seg, token, intent)
        self._trading_symbols: dict[str, str] = {}
        self._lock = threading.RLock()

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws: Any = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._authenticated = False
        self._reconnect_count = 0
        self._last_error: Optional[str] = None
        self._last_msg_at: float = 0.0
        self._started_at: float = 0.0
        self._fatal_auth = False
        self._decode_failures = 0
        self._messages_ok = 0
        self._protocol = "native_batch_apifeed_hs"

    # --- public API (thread-safe) ----------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._thread_main, name="kotak-sfeed", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._close_ws(), loop)
        if self._thread:
            self._thread.join(timeout=timeout)
        self._connected.clear()
        self._authenticated = False
        self._emit_status("stopped")

    def is_connected(self) -> bool:
        return self._connected.is_set() and self._authenticated

    def status(self) -> dict[str, Any]:
        with self._lock:
            subs = sorted(
                [
                    {"exchange_segment": s, "instrument_token": t, "intent": i}
                    for s, t, i in self._subscriptions
                ],
                key=lambda x: (x["intent"], x["exchange_segment"], x["instrument_token"]),
            )
        feed_url = self.credentials.feed_url
        # Never return query-bearing URLs that might embed secrets
        if isinstance(feed_url, str) and "?" in feed_url:
            feed_url = feed_url.split("?", 1)[0]
        return {
            "connected": self.is_connected(),
            "authenticated": self._authenticated,
            "protocol": self._protocol,
            "fatal_auth": self._fatal_auth,
            "reconnect_count": self._reconnect_count,
            "subscriptions": len(subs),
            "subscription_detail": subs[:50],
            "last_error": sanitize_error_text(self._last_error) if self._last_error else None,
            "last_msg_age_sec": (
                (time.time() - self._last_msg_at) if self._last_msg_at else None
            ),
            "messages_ok": self._messages_ok,
            "decode_failures": self._decode_failures,
            "feed_url": feed_url,
            "uptime_sec": (time.time() - self._started_at) if self._started_at else 0,
        }

    def subscribe(
        self,
        tokens: Iterable[SubToken | tuple[str, str]],
        *,
        intent: str = "depth",
    ) -> None:
        intent = self._validate_intent(intent)
        toks = [self._as_token(t) for t in tokens]
        if not toks:
            return
        with self._lock:
            for t in toks:
                self._subscriptions.add((t.exchange_segment, t.instrument_token, intent))
        self._run_coro(self._subscribe(toks, intent))

    def unsubscribe(
        self,
        tokens: Iterable[SubToken | tuple[str, str]],
        *,
        intent: str = "depth",
    ) -> None:
        intent = self._validate_intent(intent)
        toks = [self._as_token(t) for t in tokens]
        if not toks:
            return
        with self._lock:
            for t in toks:
                self._subscriptions.discard(
                    (t.exchange_segment, t.instrument_token, intent)
                )
                # Drop symbol map only if no remaining intents for token.
                still = any(
                    s == t.exchange_segment and tok == t.instrument_token
                    for s, tok, _ in self._subscriptions
                )
                if not still:
                    self._trading_symbols.pop(t.inputtoken, None)
        self._run_coro(self._unsubscribe(toks, intent))

    def wait_connected(self, timeout: float = 30.0) -> bool:
        return self._connected.wait(timeout=timeout) and self._authenticated

    # --- thread / loop ---------------------------------------------------

    def _thread_main(self) -> None:
        try:
            import websockets  # noqa: F401
        except ImportError as e:
            self._last_error = "websockets package not installed"
            logger.error("%s", self._last_error)
            self._emit_status("error", error=self._last_error)
            raise RuntimeError(self._last_error) from e

        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_forever())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
            self._loop = None

    async def _run_forever(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if self._fatal_auth:
                self._emit_status("auth_failed_fatal", error=self._last_error)
                break
            try:
                await self._connect_and_pump()
                backoff = 1.0
            except Exception as e:
                err = sanitize_error_text(e)
                self._last_error = err
                self._authenticated = False
                self._connected.clear()
                logger.warning("kotak_ws_disconnected: %s", err)
                self._emit_status("disconnected", error=err)
                if self._stop.is_set() or self._fatal_auth:
                    break
                self._reconnect_count += 1
                self._emit_status("reconnecting", backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(self.max_backoff_sec, backoff * 2)

    async def _connect_and_pump(self) -> None:
        import websockets

        url = self.credentials.feed_url
        logger.info("kotak_ws_connecting url=%s", url)
        async with websockets.connect(
            url,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_size=8 * 1024 * 1024,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            await self._authenticate(ws)
            self._authenticated = True
            self._connected.set()
            self._emit_status("connected")
            await self._resubscribe_all(ws)
            async for raw in ws:
                if self._stop.is_set():
                    break
                self._last_msg_at = time.time()
                if isinstance(raw, (bytes, bytearray)):
                    self._handle_binary(bytes(raw))
                else:
                    self._handle_text(str(raw))

    async def _authenticate(self, ws: Any) -> None:
        frame = {
            "user": self.credentials.ws_auth_user(),
            "auth": self.credentials.ws_auth_token(),
            "format": "native_batch",
            "source": "NEOTRADEAPI",
            "platform": "api",
            "version": "1.0",
            "sdk_version": 1.1,
            "sdk_date": "2026-01-01",
            "conn_req_time": int(time.time() * 1000),
            "sessionValidation": "true",
        }
        await ws.send(json.dumps(frame))
        data = None
        for _ in range(12):
            raw = await asyncio.wait_for(ws.recv(), timeout=12.0)
            if isinstance(raw, (bytes, bytearray)):
                continue
            data = json.loads(raw)
            code = data.get("message_code")
            if code == MSG_AUTH_FAIL:
                self._fatal_auth = True
                raise RuntimeError("Kotak WS auth failed (credentials/session rejected)")
            if code in MSG_AUTH_RESPONSE_CODES:
                break
        if data is None or data.get("message_code") not in MSG_AUTH_RESPONSE_CODES:
            self._fatal_auth = True
            raise RuntimeError("Unexpected Kotak WS auth response (fatal)")
        if data.get("format") == "native_fallback":
            self._fatal_auth = True
            raise RuntimeError("Server downgraded to native_fallback — unsupported")
        dividers: dict[int, int] = {}
        for name, info in (data.get("exchanges") or {}).items():
            if not isinstance(info, dict):
                continue
            exch_id = info.get("value", EXCHANGE_NAME_TO_ID.get(str(name).lower()))
            if exch_id is not None:
                dividers[int(exch_id)] = int(info.get("divider") or 100)
        if dividers:
            self._dividers = dividers
        logger.info("kotak_ws_authenticated dividers=%s", self._dividers)

    async def _resubscribe_all(self, ws: Any) -> None:
        with self._lock:
            by_intent: dict[str, list[SubToken]] = {}
            for seg, tok, intent in self._subscriptions:
                by_intent.setdefault(intent, []).append(SubToken(seg, tok))
        for intent, toks in by_intent.items():
            await self._send_subscribe(ws, _SUBSCRIBE_EVENTS[intent], toks)

    async def _subscribe(self, tokens: list[SubToken], intent: str) -> None:
        ws = self._ws
        if ws is None or not self._authenticated:
            return  # stored; will flush on reconnect
        with self._lock:
            projected = len(self._subscriptions)
        if projected > self.max_subscriptions:
            raise RuntimeError(
                f"Subscription limit exceeded: {projected} > {self.max_subscriptions}"
            )
        await self._send_subscribe(ws, _SUBSCRIBE_EVENTS[intent], tokens)

    async def _unsubscribe(self, tokens: list[SubToken], intent: str) -> None:
        ws = self._ws
        if ws is None or not self._authenticated:
            return
        await ws.send(
            json.dumps(
                {
                    "event": _UNSUBSCRIBE_EVENTS[intent],
                    "inputtoken": ",".join(t.inputtoken for t in tokens),
                }
            )
        )

    async def _send_subscribe(self, ws: Any, event: str, tokens: list[SubToken]) -> None:
        if not tokens:
            return
        await ws.send(
            json.dumps(
                {
                    "event": event,
                    "inputtoken": ",".join(t.inputtoken for t in tokens),
                    "ack_symbol": True,
                }
            )
        )

    async def _close_ws(self) -> None:
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    def _handle_binary(self, frame: bytes) -> None:
        for packet in split_batch(frame):
            try:
                msg = decode_packet(packet, self._dividers)
            except Exception as e:
                self._decode_failures += 1
                logger.warning("decode_packet failed: %s", sanitize_error_text(e))
                continue
            if msg is None:
                self._decode_failures += 1
                continue
            if isinstance(msg, (MarketPicture, MiniTouch, IndexTick)):
                key = f"{msg.exchange_segment}|{msg.instrument_token}"
                sym = self._trading_symbols.get(key)
                if sym:
                    msg.trading_symbol = sym
                elif isinstance(msg, IndexTick) and msg.name:
                    sym = self._trading_symbols.get(
                        f"{msg.exchange_segment}|{msg.name}"
                    )
                    if sym:
                        msg.trading_symbol = sym
            if self.on_message:
                try:
                    self.on_message(msg)
                    self._messages_ok += 1
                except Exception as e:
                    logger.exception("on_message handler error: %s", sanitize_error_text(e))

    def _handle_text(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            self._decode_failures += 1
            return
        if not isinstance(data, dict):
            return
        if data.get("message_code") == MSG_AUTH_FAIL:
            self._fatal_auth = True
            self._last_error = "Kotak WS auth failed during session"
            self._emit_status("auth_failed", error=self._last_error)
            self._stop.set()
            return
        if data.get("message_code") != MSG_SUBSCRIBE_ACK:
            return
        # Ack shapes vary: trading_symbols map OR data{input:{trading_symbols}}
        mapping = data.get("trading_symbols")
        if isinstance(mapping, dict):
            for key, symbol in mapping.items():
                if isinstance(key, str) and isinstance(symbol, str):
                    self._trading_symbols[key] = symbol
                elif isinstance(key, str) and isinstance(symbol, dict):
                    ts = symbol.get("trading_symbols") or symbol.get("trading_symbol")
                    if ts:
                        self._trading_symbols[key] = str(ts)
        payload = data.get("data")
        if isinstance(payload, dict):
            for key, info in payload.items():
                if isinstance(info, dict):
                    ts = info.get("trading_symbols") or info.get("trading_symbol")
                    if ts and isinstance(key, str):
                        self._trading_symbols[key] = str(ts)

    def _emit_status(self, state: str, **extra: Any) -> None:
        if not self.on_status:
            return
        payload = {"state": state, **self.status(), **extra}
        try:
            self.on_status(payload)
        except Exception:
            pass

    def _run_coro(self, coro: Any) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            # Not connected yet — subscription already stored for resubscribe.
            if asyncio.iscoroutine(coro):
                coro.close()
            return
        fut = asyncio.run_coroutine_threadsafe(coro, loop)

        def _done(f: Any) -> None:
            try:
                f.result()
            except Exception as e:
                self._last_error = str(e)
                logger.warning("kotak_ws_coro_failed: %s", e)

        fut.add_done_callback(_done)

    @staticmethod
    def _as_token(t: SubToken | tuple[str, str]) -> SubToken:
        if isinstance(t, SubToken):
            return t
        return SubToken(str(t[0]), str(t[1]))

    @staticmethod
    def _validate_intent(intent: str) -> str:
        if intent not in _SUBSCRIBE_EVENTS:
            raise ValueError(
                f"Unknown subscribe intent {intent!r}; "
                f"expected one of {sorted(_SUBSCRIBE_EVENTS)}"
            )
        return intent
