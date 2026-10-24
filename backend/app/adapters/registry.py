"""Select market-data adapter from config (demo default)."""
from __future__ import annotations

from functools import lru_cache

from app.adapters.base import MarketDataAdapter
from app.adapters.demo import DemoAdapter
from app.config import config


@lru_cache(maxsize=1)
def get_market_adapter() -> MarketDataAdapter:
    """Return the configured adapter. MVP only ships ``DemoAdapter``."""
    name = (config.market_data_adapter or "demo").strip().lower()
    if name == "demo":
        return DemoAdapter()
    # Future: live Kotak/Yahoo adapters registered here without rewriting callers
    return DemoAdapter()
