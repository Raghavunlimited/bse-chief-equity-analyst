"""Market-data adapters (quotes, bars, OI, financials)."""

from app.adapters.base import MarketDataAdapter, Provenance
from app.adapters.demo import DemoAdapter
from app.adapters.registry import get_market_adapter

__all__ = ["MarketDataAdapter", "Provenance", "DemoAdapter", "get_market_adapter"]
