"""Market-data adapters — live only."""

from app.adapters.base import MarketDataAdapter, Provenance
from app.adapters.live_yahoo import LiveYahooAdapter
from app.adapters.registry import DemoAdapterForbidden, get_market_adapter

__all__ = [
    "MarketDataAdapter",
    "Provenance",
    "LiveYahooAdapter",
    "get_market_adapter",
    "DemoAdapterForbidden",
]
