"""
Strict market-data contracts — EOD vs LTP must never be conflated.

States (market_data_state):
  LIVE       — broker/session LTP within age threshold (Kotak WS)
  FALLBACK   — non-broker research tape within age (e.g. Yahoo 5m), not broker live
  DELAYED    — delayed/research quote outside a claim of real-time broker feed
  STALE      — quote age exceeded threshold during regular hours
  EOD        — settled daily close (swing / regime); never an LTP
  UNAVAILABLE— no usable price
  PRE_MARKET / POST_MARKET / WEEKEND / HOLIDAY / ERROR — session / fault

Provenance for UI (narrow): live | fallback | delayed | stale | eod | unavailable
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

PriceKind = Literal["eod_close", "ltp"]
Timeframe = Literal["1d", "5m", "1m", "ltp", "unknown"]

# Canonical feed / market-data states used in API + UI
MarketDataState = Literal[
    "LIVE",
    "FALLBACK",
    "DELAYED",
    "STALE",
    "EOD",
    "UNAVAILABLE",
    "PRE_MARKET",
    "POST_MARKET",
    "WEEKEND",
    "HOLIDAY",
    "ERROR",
]

# Legacy FeedStatus kept for older callers; prefer market_data_state
FeedStatus = Literal[
    "LIVE",
    "FALLBACK",
    "DELAYED",
    "STALE",
    "EOD",
    "UNAVAILABLE",
    "POST_MARKET",
    "PRE_MARKET",
    "WEEKEND",
    "HOLIDAY",
    "ERROR",
]

ProviderClass = Literal["broker", "research_fallback", "eod", "unknown"]
Provenance = Literal["live", "fallback", "delayed", "stale", "eod", "unavailable"]

# Sources treated as broker websocket (not research fallback)
BROKER_LIVE_SOURCES = frozenset({"kotak_neo_ws", "kotak_ws", "kotak_neo"})
RESEARCH_FALLBACK_SOURCES = frozenset(
    {"yahoo_chart", "yahoo", "yahoo_eod", "yahoo_finance"}
)


def provider_class_for_source(source: str | None) -> ProviderClass:
    s = (source or "").strip().lower()
    if s in BROKER_LIVE_SOURCES:
        return "broker"
    if s in RESEARCH_FALLBACK_SOURCES or s.startswith("yahoo"):
        return "research_fallback"
    if s in ("kotak", "kotak_eod", "nse", "nse_bhav"):
        return "eod"
    return "unknown"


def provenance_for_state(state: MarketDataState) -> Provenance:
    if state == "LIVE":
        return "live"
    if state == "FALLBACK":
        return "fallback"
    if state == "STALE":
        return "stale"
    if state == "EOD":
        return "eod"
    if state in ("UNAVAILABLE", "ERROR"):
        return "unavailable"
    # PRE/POST/WEEKEND/HOLIDAY/DELAYED → delayed (not current broker live)
    return "delayed"


def is_broker_live_claim(state: MarketDataState, source: str | None) -> bool:
    """True only when we may label the quote as broker LIVE."""
    return state == "LIVE" and provider_class_for_source(source) == "broker"


@dataclass(frozen=True)
class EODBar:
    """One settled (or historical) OHLC bar — never an intraday LTP."""

    symbol: str
    trade_date: str  # YYYY-MM-DD (session date)
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str  # kotak | yahoo_eod | …
    price_kind: PriceKind = "eod_close"
    timeframe: Timeframe = "1d"
    market_data_state: MarketDataState = "EOD"
    ingested_at_unix: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provenance"] = "eod"
        d["is_current_live"] = False
        return d


@dataclass(frozen=True)
class IntradayBar:
    """
    One intraday OHLCV bar (typically 5m). Contract type for honesty;
    persistence is a later phase — bars may still be ephemeral today.
    """

    symbol: str
    bar_start_unix: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    timeframe: Timeframe = "5m"
    complete: bool = True
    market_data_state: MarketDataState = "FALLBACK"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["price_kind"] = "ltp"
        d["is_current_live"] = False
        d["provenance"] = provenance_for_state(self.market_data_state)
        return d


@dataclass(frozen=True)
class LiveQuote:
    """
    Intraday last-traded snapshot.

    quote_ts_unix: exchange / provider event time (seconds UTC).
    fetched_at_unix: when this process obtained the snapshot (ingestion time).
    age_sec: now - quote_ts_unix (staleness input).
    market_data_state: truthful display state (LIVE only for broker + fresh).
    """

    symbol: str
    ltp: Optional[float]
    quote_ts_unix: float
    fetched_at_unix: float
    age_sec: float
    feed_status: FeedStatus
    source: str
    price_kind: PriceKind = "ltp"
    timeframe: Timeframe = "ltp"
    market_data_state: MarketDataState = "UNAVAILABLE"
    provider_class: ProviderClass = "unknown"
    is_current_live: bool = False
    prev_close: Optional[float] = None
    change_pct: Optional[float] = None
    session_open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    last_volume: Optional[float] = None
    session_volume: Optional[float] = None
    vwap: Optional[float] = None
    currency: str = "INR"
    exchange: Optional[str] = None
    closes_5m: tuple[float, ...] = field(default_factory=tuple)
    volumes_5m: tuple[float, ...] = field(default_factory=tuple)
    bars_5m: int = 0
    yahoo_symbol: Optional[str] = None
    error: Optional[str] = None
    # Phase 2 — Kotak Neo tick / L2 fields
    instrument_token: Optional[str] = None
    exchange_segment: Optional[str] = None
    ltq: Optional[float] = None
    atp: Optional[float] = None
    oi: Optional[float] = None
    prev_day_oi: Optional[float] = None
    depth_bids: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    depth_asks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    obi: Optional[float] = None
    spread_pct: Optional[float] = None
    exchange_timestamp: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["closes_5m"] = list(self.closes_5m)
        d["volumes_5m"] = list(self.volumes_5m)
        d["depth_bids"] = list(self.depth_bids)
        d["depth_asks"] = list(self.depth_asks)
        d["price"] = self.ltp
        d["last_ts"] = int(self.quote_ts_unix) if self.quote_ts_unix else None
        d["as_of"] = _iso_z(self.fetched_at_unix)
        d["quote_ts_iso"] = (
            _iso_z(self.quote_ts_unix) if self.quote_ts_unix else None
        )
        d["ingestion_ts_iso"] = _iso_z(self.fetched_at_unix)
        state = self.market_data_state or self.feed_status
        d["market_data_state"] = state
        d["provenance"] = provenance_for_state(state)  # type: ignore[arg-type]
        d["is_current_live"] = bool(self.is_current_live) and is_broker_live_claim(
            state, self.source  # type: ignore[arg-type]
        )
        d["is_last_observation"] = not d["is_current_live"] and self.ltp is not None
        d["provider_class"] = self.provider_class or provider_class_for_source(
            self.source
        )
        return d


@dataclass(frozen=True)
class FeedHealth:
    """Aggregate live-feed health for a desk poll."""

    feed_status: FeedStatus
    market_data_state: MarketDataState
    in_regular_hours: bool
    session_label: str
    stale_sec_threshold: float
    quotes_ok: int
    quotes_stale: int
    quotes_error: int
    quotes_fallback: int
    live_calls_allowed: bool
    broker_live: bool
    message: str
    as_of: str
    calendar_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iso_z(ts: float) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
