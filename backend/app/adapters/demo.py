"""REMOVED — DemoAdapter deleted in Phase 1.

Importing this module is a hard failure so no code path can silently revive demo.
"""

raise RuntimeError(
    "app.adapters.demo was removed. Demo/mock market data is forbidden. "
    "Use app.adapters.live_yahoo.LiveYahooAdapter via get_market_adapter()."
)
