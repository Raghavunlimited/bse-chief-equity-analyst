"""Market-data adapter ABC — prices, OI, financials with provenance (no demo)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, TypedDict

# demo intentionally removed — adapters must be live / delayed / stale only
Provenance = Literal["live", "delayed", "stale"]


class ProvenanceFields(TypedDict):
    provenance: Provenance
    as_of: str  # ISO-8601 UTC
    source: str  # adapter id, e.g. "yahoo_live", "kotak"


class QuotePayload(ProvenanceFields):
    symbol: str
    last: float
    open: float
    high: float
    low: float
    prev_close: float
    change_pct: float
    volume: float
    currency: str


class BarBar(TypedDict):
    trade_date: str  # ISO date or datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsPayload(ProvenanceFields):
    symbol: str
    interval: str
    bars: list[BarBar]


class OiPayload(ProvenanceFields):
    symbol: str
    open_interest: float
    oi_change: float
    oi_change_pct: float


class FinancialsPayload(ProvenanceFields):
    symbol: str
    pe: float | None
    pb: float | None
    market_cap: float | None
    eps: float | None
    dividend_yield: float | None
    extras: dict


class MarketDataAdapter(ABC):
    """Boundary for all market-data reads used by desks and enrichment."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Stable adapter id written into payload ``source``."""

    @abstractmethod
    def get_quote(self, symbol: str) -> QuotePayload:
        """Latest LTP / session quote for ``symbol`` (never EOD close labeled as LTP)."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        interval: str = "1d",
        lookback: int = 60,
    ) -> BarsPayload:
        """OHLCV series — daily bars are EOD settlement unless interval is intraday."""

    @abstractmethod
    def get_oi(self, symbol: str) -> OiPayload:
        """Open interest snapshot (commodities / F&O). Must raise if unavailable."""

    @abstractmethod
    def get_financials(self, symbol: str) -> FinancialsPayload:
        """Fundamentals snapshot; numeric fields may be None when unknown."""
