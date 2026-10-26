"""
LiveQuote resolution boundary.

Order of preference (verified):
  1. Kotak Neo WebSocket hub quote when connected + cached for the symbol
  2. Yahoo chart 5m research tape — only if ALLOW_YAHOO_LTP_FALLBACK is true

Never labels Yahoo as broker LIVE (Phase 1 annotate_live_quote). Never invents
demo prices. Missing broker + disabled fallback → ERROR / UNAVAILABLE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.config import config
from app.market_session import annotate_live_quote, session_snapshot
from app.market_types import LiveQuote


@dataclass(frozen=True)
class LiveQuoteResolution:
    quote: LiveQuote
    path: str  # kotak_neo_ws | yahoo_chart_fallback | unavailable
    yahoo_fallback_allowed: bool
    kotak_ws_connected: bool


def yahoo_fallback_allowed() -> bool:
    return bool(getattr(config, "allow_yahoo_ltp_fallback", True))


def _kotak_connected() -> bool:
    try:
        from app.kotak.feed_hub import get_feed_hub

        st = get_feed_hub().status()
        return bool((st.get("ws") or {}).get("connected"))
    except Exception:
        return False


def _kotak_quote(yahoo_symbol: str) -> Optional[LiveQuote]:
    try:
        from dataclasses import replace

        from app.kotak.feed_hub import get_feed_hub

        hub = get_feed_hub()
        st = hub.status()
        if not (st.get("ws") or {}).get("connected"):
            return None
        q = hub.quote_for_yahoo_symbol(yahoo_symbol)
        if q is None or q.ltp is None:
            return None
        sess = session_snapshot()
        return annotate_live_quote(
            replace(q, yahoo_symbol=yahoo_symbol, source=q.source or "kotak_neo_ws"),
            session=sess,
        )
    except Exception:
        return None


def _yahoo_quote(yahoo_symbol: str) -> LiveQuote:
    from app import live_quotes

    # Direct Yahoo fetch (bypasses provider recursion)
    return live_quotes.yahoo_chart_quote(yahoo_symbol)


def _unavailable(yahoo_symbol: str, err: str) -> LiveQuote:
    from app import live_quotes

    return live_quotes.unavailable_quote(yahoo_symbol, err)


def resolve_live_quote(yahoo_symbol: str) -> LiveQuoteResolution:
    """Resolve one symbol through the broker → optional Yahoo fallback boundary."""
    allow_fb = yahoo_fallback_allowed()
    connected = _kotak_connected()
    kq = _kotak_quote(yahoo_symbol)
    if kq is not None:
        return LiveQuoteResolution(
            quote=kq,
            path="kotak_neo_ws",
            yahoo_fallback_allowed=allow_fb,
            kotak_ws_connected=connected,
        )
    if allow_fb:
        yq = _yahoo_quote(yahoo_symbol)
        return LiveQuoteResolution(
            quote=yq,
            path="yahoo_chart_fallback",
            yahoo_fallback_allowed=True,
            kotak_ws_connected=connected,
        )
    return LiveQuoteResolution(
        quote=_unavailable(
            yahoo_symbol,
            "kotak_ws_unavailable_and_yahoo_fallback_disabled",
        ),
        path="unavailable",
        yahoo_fallback_allowed=False,
        kotak_ws_connected=connected,
    )


def provider_policy_public() -> dict[str, Any]:
    return {
        "broker": "kotak_neo_ws",
        "broker_protocol": "native_batch_apifeed_hs",
        "broker_protocol_note": (
            "Verified against Kotak Neo Market Data WebSocket Developer Guide "
            "(native_batch on feedUrl/apifeed). Kotak announced SFeed migration "
            "deadline 15 Sep 2026 — this desk still uses the HS/apifeed client."
        ),
        "research_fallback": "yahoo_chart",
        "yahoo_ltp_fallback_allowed": yahoo_fallback_allowed(),
        "demo_allowed": False,
        "claims": {
            # Protocol/code paths exist; do not treat as live-verified coverage
            "ltp": "protocol_supported_not_live_e2e_verified",
            "depth_l2": "subscribe_path_exists_not_live_e2e_verified",
            "fno_tokens": "subscribe_path_exists_not_live_e2e_verified",
            "verified_live_e2e_this_build": False,
        },
    }
