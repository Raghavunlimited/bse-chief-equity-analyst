"""
Tick ordering / validation helpers for Kotak feed hub.

Pure functions — unit-tested without a live WebSocket.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Redact session-looking tokens from error strings before logging / API
_SECRETISH = re.compile(
    r"(?i)(auth|sid|token|mpin|password|secret|bearer|api[_-]?key|"
    r"consumer[_-]?key|totp|session)\s*[:=]\s*['\"]?[\w\-./=+]+"
)
_UUIDISH = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)
def sanitize_error_text(text: Any, *, max_len: int = 240) -> str:
    """Strip credential-like substrings from exception / status text."""
    s = str(text or "")
    s = _SECRETISH.sub(r"\1=[REDACTED]", s)
    s = _UUIDISH.sub("[REDACTED]", s)
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def should_accept_tick(
    *,
    incoming_ts: Optional[float],
    previous_ts: Optional[float],
    incoming_ltp: Optional[float],
) -> tuple[bool, str]:
    """
    Decide whether to replace the cached quote.

    - Reject missing / non-positive LTP
    - Reject strictly older exchange timestamps (out-of-order / late replay)
    - Accept equal or newer timestamps (duplicate refresh OK)
    """
    if incoming_ltp is None:
        return False, "missing_ltp"
    try:
        px = float(incoming_ltp)
    except (TypeError, ValueError):
        return False, "invalid_ltp"
    if px <= 0:
        return False, "non_positive_ltp"

    if incoming_ts is None:
        return True, "no_ts_accept"
    try:
        ts = float(incoming_ts)
    except (TypeError, ValueError):
        return False, "invalid_ts"
    if ts <= 0:
        return True, "zero_ts_accept"

    if previous_ts is None:
        return True, "first"
    try:
        prev = float(previous_ts)
    except (TypeError, ValueError):
        return True, "bad_prev_accept"

    if ts < prev:
        return False, "out_of_order"
    return True, "ok"


def public_ws_status(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Strip subscription detail noise; keep operator-safe fields."""
    st = dict(raw or {})
    # Never echo feed URL query strings that might carry tokens (unlikely but safe)
    feed_url = st.get("feed_url")
    if isinstance(feed_url, str) and "?" in feed_url:
        st["feed_url"] = feed_url.split("?", 1)[0]
    if st.get("last_error"):
        st["last_error"] = sanitize_error_text(st["last_error"])
    # Cap subscription_detail exposure
    detail = st.get("subscription_detail")
    if isinstance(detail, list) and len(detail) > 20:
        st["subscription_detail"] = detail[:20]
        st["subscription_detail_truncated"] = True
    return st
