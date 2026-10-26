"""Select market-data adapter — live only. Demo is a hard error."""
from __future__ import annotations

from functools import lru_cache

from app.adapters.base import MarketDataAdapter
from app.adapters.live_yahoo import LiveYahooAdapter
from app.config import config


class DemoAdapterForbidden(RuntimeError):
    """Raised when config still requests the removed demo adapter."""


@lru_cache(maxsize=1)
def get_market_adapter() -> MarketDataAdapter:
    name = (config.market_data_adapter or "live").strip().lower()
    if name in ("demo", "mock", "synthetic", "fake"):
        raise DemoAdapterForbidden(
            f"MARKET_DATA_ADAPTER={name!r} is forbidden. "
            "Demo/mock adapters were removed in Phase 1. Set MARKET_DATA_ADAPTER=live."
        )
    if name in ("live", "yahoo", "yahoo_live", "kotak"):
        # Phase 1: Yahoo LTP + local EOD. Phase 2 swaps ticks to Kotak WS.
        return LiveYahooAdapter()
    raise DemoAdapterForbidden(
        f"Unknown MARKET_DATA_ADAPTER={name!r}. Allowed: live (Phase 1 Yahoo/Kotak EOD)."
    )


def clear_adapter_cache() -> None:
    get_market_adapter.cache_clear()
