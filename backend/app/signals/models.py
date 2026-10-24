"""
Signal call schema — consultant desk output.

Canonical shape: desk, symbol, side (BUY/SELL/HOLD), confidence 0–100,
thesis, entry/stop/targets, as_of, expires_at, tags, sources, disclaimer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

Side = Literal["BUY", "SELL", "HOLD"]
Desk = Literal["swing", "intraday", "mcx"]

DISCLAIMER = (
    "Research / education only. Not investment advice. Not a profit guarantee. "
    "Past patterns do not ensure future results. Capital at risk."
)
# Alias used by consultant router / daily snapshot
RESEARCH_DISCLAIMER = DISCLAIMER


@dataclass
class SignalCall:
    """Normalized consultant call across swing / intraday / MCX desks."""

    desk: Desk
    symbol: str
    side: Side
    confidence: float  # 0–100
    thesis: str
    entry: float | None = None
    stop: float | None = None
    targets: dict[str, float] = field(default_factory=dict)
    as_of: str | None = None
    expires_at: str | None = None
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    id: str = field(default_factory=lambda: str(uuid4()))
    horizon: str = "swing"
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        side = str(self.side or "HOLD").upper()
        if side not in ("BUY", "SELL", "HOLD"):
            side = "HOLD"
        object.__setattr__(self, "side", side)
        conf = round(max(0.0, min(100.0, float(self.confidence or 0))), 1)
        object.__setattr__(self, "confidence", conf)
        object.__setattr__(self, "symbol", str(self.symbol or "").upper())
        if not self.disclaimer:
            object.__setattr__(self, "disclaimer", DISCLAIMER)
        if self.targets is None:
            object.__setattr__(self, "targets", {})
        if self.tags is None:
            object.__setattr__(self, "tags", [])
        if self.sources is None:
            object.__setattr__(self, "sources", [])
        if self.context is None:
            object.__setattr__(self, "context", {})

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d.get("context"):
            d.pop("context", None)
        return d


def make_call(
    *,
    desk: str,
    symbol: str,
    side: str,
    confidence: float,
    thesis: str,
    entry: float | None = None,
    stop: float | None = None,
    targets: dict[str, float] | None = None,
    tags: list[str] | None = None,
    sources: list[str] | None = None,
    horizon: str = "swing",
    extras: dict[str, Any] | None = None,
    ttl_hours: float = 24.0,
    as_of: str | None = None,
    expires_at: str | None = None,
    disclaimer: str | None = None,
) -> dict[str, Any]:
    """Build a SignalCall dict (API-ready). Preferred factory for desk adapters."""
    now = datetime.now(timezone.utc)
    call = SignalCall(
        desk=desk,  # type: ignore[arg-type]
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        confidence=confidence,
        thesis=thesis,
        entry=entry,
        stop=stop,
        targets=targets or {},
        tags=tags or [],
        sources=sources or [],
        horizon=horizon,
        as_of=as_of or now.isoformat(),
        expires_at=expires_at or (now + timedelta(hours=ttl_hours)).isoformat(),
        disclaimer=disclaimer or DISCLAIMER,
        context=dict(extras or {}),
    )
    return call.to_dict()
