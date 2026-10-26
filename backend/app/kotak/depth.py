"""
5-level market depth (L2) helpers — Order Book Imbalance and Bid-Ask Spread %.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from app.kotak.protocol import DepthLevel


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Normalized L2 book with derived microstructure metrics."""

    bids: tuple[DepthLevel, ...] = field(default_factory=tuple)
    asks: tuple[DepthLevel, ...] = field(default_factory=tuple)
    bid_qty_sum: float = 0.0
    ask_qty_sum: float = 0.0
    obi: Optional[float] = None
    spread: Optional[float] = None
    spread_pct: Optional[float] = None
    mid: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bids": [b.to_dict() for b in self.bids],
            "asks": [a.to_dict() for a in self.asks],
            "bid_qty_sum": self.bid_qty_sum,
            "ask_qty_sum": self.ask_qty_sum,
            "obi": self.obi,
            "spread": self.spread,
            "spread_pct": self.spread_pct,
            "mid": self.mid,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "levels": max(len(self.bids), len(self.asks)),
        }


def order_book_imbalance(bid_qty: float, ask_qty: float) -> Optional[float]:
    """OBI = (Σ bid qty − Σ ask qty) / (Σ bid qty + Σ ask qty). Range [-1, 1]."""
    total = float(bid_qty) + float(ask_qty)
    if total <= 0:
        return None
    return (float(bid_qty) - float(ask_qty)) / total


def bid_ask_spread_pct(best_bid: float, best_ask: float) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (spread, spread_pct, mid). spread_pct = (ask−bid)/mid × 100."""
    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        return None, None, None
    mid = (best_bid + best_ask) / 2.0
    spread = best_ask - best_bid
    if mid <= 0:
        return spread, None, mid
    return spread, (spread / mid) * 100.0, mid


def build_order_book(
    bids: Sequence[DepthLevel] | None,
    asks: Sequence[DepthLevel] | None,
    *,
    max_levels: int = 5,
) -> OrderBookSnapshot:
    """Take up to ``max_levels`` bid/ask rows and compute OBI + spread %."""
    bid_rows = tuple(list(bids or [])[:max_levels])
    ask_rows = tuple(list(asks or [])[:max_levels])
    bid_sum = float(sum(b.quantity for b in bid_rows))
    ask_sum = float(sum(a.quantity for a in ask_rows))
    best_bid = bid_rows[0].price if bid_rows else None
    best_ask = ask_rows[0].price if ask_rows else None
    spread = spread_pct = mid = None
    if best_bid is not None and best_ask is not None:
        spread, spread_pct, mid = bid_ask_spread_pct(best_bid, best_ask)
    return OrderBookSnapshot(
        bids=bid_rows,
        asks=ask_rows,
        bid_qty_sum=bid_sum,
        ask_qty_sum=ask_sum,
        obi=order_book_imbalance(bid_sum, ask_sum),
        spread=spread,
        spread_pct=spread_pct,
        mid=mid,
        best_bid=best_bid,
        best_ask=best_ask,
    )
