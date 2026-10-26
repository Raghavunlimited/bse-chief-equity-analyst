"""
Kotak Neo TOTP session — obtains sid / Auth / hsServerId / feedUrl for the live WS.

Fails loud when credentials are missing. Supports:
  1. Full login: consumer_key + mobile + ucc + totp (+ optional totp_secret) + mpin
  2. Injected session: KOTAK_SESSION_SID + KOTAK_SESSION_AUTH + KOTAK_UCC (+ feed URL)
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_LOGIN_BASE = "https://mis.kotaksecurities.com"
_LOGIN_PATH = "/login/1.0/tradeApiLogin"
_VALIDATE_PATH = "/login/1.0/tradeApiValidate"
_CONFIG_URL = "https://lapi.kotaksecurities.com/5config/config"
_DEFAULT_FEED = "wss://sfeed.kotaksecurities.com/apifeed"
_NEO_FIN_KEY = "neotradeapi"


@dataclass
class SessionCredentials:
    """Live Kotak session material required for WebSocket + authenticated REST."""

    ucc: str
    sid: str
    auth: str  # trading session token (Auth header)
    hs_server_id: str = ""
    feed_url: str = _DEFAULT_FEED
    base_url: str = "https://cis.kotaksecurities.com"
    data_center: str = ""
    consumer_key: str = ""
    source: str = "totp_validate"  # totp_validate | env_inject

    def ws_auth_user(self) -> str:
        return self.ucc

    def ws_auth_token(self) -> str:
        # native_batch auth frame: auth defaults to trading sid (SDK behaviour).
        return self.sid

    def public_status(self) -> dict[str, Any]:
        return {
            "ucc": self.ucc,
            "sid_present": bool(self.sid),
            "auth_present": bool(self.auth),
            "hs_server_id": self.hs_server_id or None,
            "feed_url": self.feed_url,
            "base_url": self.base_url,
            "data_center": self.data_center or None,
            "source": self.source,
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Never expose full secrets in API responses — use public_status.
        d["auth"] = f"{self.auth[:6]}…" if self.auth else ""
        d["sid"] = f"{self.sid[:6]}…" if self.sid else ""
        return d


def _reload_env() -> None:
    load_dotenv(_ENV_PATH, override=True)


def consumer_key() -> Optional[str]:
    _reload_env()
    return (
        os.getenv("KOTAK_CONSUMER_KEY")
        or os.getenv("NEO_CONSUMER_KEY")
        or os.getenv("KOTAK_NEO_CONSUMER_KEY")
        or ""
    ).strip() or None


def to_websocket_scheme(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = {"https": "wss", "http": "ws"}.get(parts.scheme, parts.scheme)
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _headers(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    key = consumer_key()
    if not key:
        raise RuntimeError(
            "KOTAK_CONSUMER_KEY missing — cannot open Kotak session. "
            "Set it in backend/.env (Neo Trade API token)."
        )
    h = {
        "Authorization": key,
        "neo-fin-key": _NEO_FIN_KEY,
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _resolve_totp(explicit: Optional[str] = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    _reload_env()
    one_shot = (os.getenv("KOTAK_TOTP") or "").strip()
    if one_shot:
        return one_shot
    secret = (os.getenv("KOTAK_TOTP_SECRET") or "").strip().replace(" ", "")
    if secret:
        try:
            import pyotp
        except ImportError as e:
            raise RuntimeError(
                "KOTAK_TOTP_SECRET set but pyotp is not installed. "
                "pip install pyotp or pass totp= explicitly."
            ) from e
        return pyotp.TOTP(secret).now()
    raise RuntimeError(
        "TOTP required: pass totp=…, or set KOTAK_TOTP / KOTAK_TOTP_SECRET in .env"
    )


def _resolve_feed_url(
    validate_data: dict[str, Any],
    *,
    explicit: Optional[str] = None,
) -> str:
    if explicit and explicit.strip():
        return to_websocket_scheme(explicit.strip())
    feed = (validate_data.get("feedUrl") or "").strip()
    if feed:
        return to_websocket_scheme(feed)
    dc = (validate_data.get("dataCenter") or "").strip()
    if dc:
        try:
            r = requests.get(
                _CONFIG_URL,
                params={
                    "platform": "api",
                    "environment": "prod",
                    "dataCenter": dc,
                },
                timeout=20,
            )
            if r.status_code == 200:
                body = r.json()
                # Config payloads vary; hunt for an apifeed / sfeed URL.
                blob = str(body)
                for candidate in _extract_urls(blob):
                    if "feed" in candidate.lower() or "sfeed" in candidate.lower():
                        return to_websocket_scheme(candidate)
                data = body.get("data") if isinstance(body, dict) else None
                if isinstance(data, dict):
                    for k in ("feedUrl", "sfeedUrl", "marketFeedUrl", "url"):
                        if data.get(k):
                            return to_websocket_scheme(str(data[k]))
        except Exception as e:
            logger.warning("config service feed lookup failed: %s", e)
    return _DEFAULT_FEED


def _extract_urls(text: str) -> list[str]:
    import re

    return re.findall(r"https?://[^\s\"'<>]+", text)


class KotakSession:
    """Process-wide Kotak trading session."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._creds: Optional[SessionCredentials] = None

    @property
    def credentials(self) -> Optional[SessionCredentials]:
        with self._lock:
            return self._creds

    def require(self) -> SessionCredentials:
        with self._lock:
            if self._creds is None:
                injected = self._try_env_inject()
                if injected:
                    self._creds = injected
                    return self._creds
                raise RuntimeError(
                    "No Kotak live session. Call POST /api/kotak/session/login "
                    "with mobile/ucc/totp/mpin, or set KOTAK_SESSION_SID + "
                    "KOTAK_SESSION_AUTH + KOTAK_UCC in backend/.env"
                )
            return self._creds

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._creds is None:
                env = self._env_session_present()
                return {
                    "authenticated": False,
                    "env_session_injectable": env,
                    "consumer_key_present": bool(consumer_key()),
                }
            return {"authenticated": True, **self._creds.public_status()}

    def clear(self) -> None:
        with self._lock:
            self._creds = None

    def set_credentials(self, creds: SessionCredentials) -> SessionCredentials:
        if not creds.ucc or not creds.sid or not creds.auth:
            raise ValueError("SessionCredentials require ucc, sid, and auth")
        if not creds.feed_url:
            creds.feed_url = _DEFAULT_FEED
        creds.feed_url = to_websocket_scheme(creds.feed_url)
        with self._lock:
            self._creds = creds
        return creds

    def login(
        self,
        *,
        mobile: Optional[str] = None,
        ucc: Optional[str] = None,
        totp: Optional[str] = None,
        mpin: Optional[str] = None,
        feed_url: Optional[str] = None,
    ) -> SessionCredentials:
        _reload_env()
        mobile = (mobile or os.getenv("KOTAK_MOBILE") or "").strip()
        ucc = (ucc or os.getenv("KOTAK_UCC") or "").strip()
        mpin = (mpin or os.getenv("KOTAK_MPIN") or "").strip()
        if not mobile or not ucc or not mpin:
            raise RuntimeError(
                "Kotak login requires mobile, ucc, and mpin "
                "(args or KOTAK_MOBILE / KOTAK_UCC / KOTAK_MPIN)"
            )
        totp_code = _resolve_totp(totp)
        view = self._totp_login(mobile=mobile, ucc=ucc, totp=totp_code)
        trade = self._totp_validate(view_sid=view["sid"], view_token=view["token"], mpin=mpin)
        feed = _resolve_feed_url(trade, explicit=feed_url or os.getenv("KOTAK_FEED_URL"))
        creds = SessionCredentials(
            ucc=str(trade.get("ucc") or ucc),
            sid=str(trade["sid"]),
            auth=str(trade["token"]),
            hs_server_id=str(trade.get("hsServerId") or view.get("hsServerId") or ""),
            feed_url=feed,
            base_url=str(trade.get("baseUrl") or "https://cis.kotaksecurities.com"),
            data_center=str(trade.get("dataCenter") or ""),
            consumer_key=consumer_key() or "",
            source="totp_validate",
        )
        return self.set_credentials(creds)

    def _totp_login(self, *, mobile: str, ucc: str, totp: str) -> dict[str, Any]:
        url = f"{_LOGIN_BASE}{_LOGIN_PATH}"
        r = requests.post(
            url,
            headers=_headers(),
            json={"mobileNumber": mobile, "ucc": ucc, "totp": totp},
            timeout=30,
        )
        try:
            body = r.json()
        except Exception as e:
            raise RuntimeError(f"tradeApiLogin non-JSON HTTP {r.status_code}") from e
        data = body.get("data") if isinstance(body, dict) else None
        if not (200 <= r.status_code <= 299) or not isinstance(data, dict):
            raise RuntimeError(f"tradeApiLogin failed HTTP {r.status_code}: {body}")
        if not data.get("token") or not data.get("sid"):
            raise RuntimeError(f"tradeApiLogin missing token/sid: {body}")
        return data

    def _totp_validate(
        self, *, view_sid: str, view_token: str, mpin: str
    ) -> dict[str, Any]:
        url = f"{_LOGIN_BASE}{_VALIDATE_PATH}"
        r = requests.post(
            url,
            headers=_headers({"sid": view_sid, "Auth": view_token}),
            json={"mpin": mpin},
            timeout=30,
        )
        try:
            body = r.json()
        except Exception as e:
            raise RuntimeError(f"tradeApiValidate non-JSON HTTP {r.status_code}") from e
        data = body.get("data") if isinstance(body, dict) else None
        if not (200 <= r.status_code <= 299) or not isinstance(data, dict):
            raise RuntimeError(f"tradeApiValidate failed HTTP {r.status_code}: {body}")
        if not data.get("token") or not data.get("sid"):
            raise RuntimeError(f"tradeApiValidate missing token/sid: {body}")
        return data

    def _env_session_present(self) -> bool:
        _reload_env()
        return bool(
            (os.getenv("KOTAK_SESSION_SID") or "").strip()
            and (os.getenv("KOTAK_SESSION_AUTH") or "").strip()
            and (os.getenv("KOTAK_UCC") or "").strip()
        )

    def _try_env_inject(self) -> Optional[SessionCredentials]:
        _reload_env()
        sid = (os.getenv("KOTAK_SESSION_SID") or "").strip()
        auth = (os.getenv("KOTAK_SESSION_AUTH") or "").strip()
        ucc = (os.getenv("KOTAK_UCC") or "").strip()
        if not (sid and auth and ucc):
            return None
        feed = (os.getenv("KOTAK_FEED_URL") or "").strip() or _DEFAULT_FEED
        return SessionCredentials(
            ucc=ucc,
            sid=sid,
            auth=auth,
            hs_server_id=(os.getenv("KOTAK_HS_SERVER_ID") or "").strip(),
            feed_url=to_websocket_scheme(feed),
            base_url=(os.getenv("KOTAK_BASE_URL") or "https://cis.kotaksecurities.com").strip(),
            data_center=(os.getenv("KOTAK_DATA_CENTER") or "").strip(),
            consumer_key=consumer_key() or "",
            source="env_inject",
        )


_session: Optional[KotakSession] = None
_session_lock = threading.Lock()


def get_kotak_session() -> KotakSession:
    global _session
    with _session_lock:
        if _session is None:
            _session = KotakSession()
        return _session
