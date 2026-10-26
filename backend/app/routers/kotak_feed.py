"""Kotak Neo session, scrip resolve, live quote / depth / bars API."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/kotak", tags=["kotak-feed"])


class LoginBody(BaseModel):
    mobile: Optional[str] = None
    ucc: Optional[str] = None
    totp: Optional[str] = None
    mpin: Optional[str] = None
    feed_url: Optional[str] = None
    start_feed: bool = True


class SubscribeBody(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    exchange_segment: str = "nse_cm"
    with_depth: bool = True


class FutureBody(BaseModel):
    underlying: str
    expiry: Optional[str] = None
    exchange_segment: str = "nse_fo"


class OptionBody(BaseModel):
    underlying: str
    expiry: str
    strike: float
    right: str
    exchange_segment: str = "nse_fo"


class UnsubscribeBody(BaseModel):
    keys: list[str]


@router.get("/session")
def session_status() -> dict[str, Any]:
    from app.kotak.session import get_kotak_session

    return get_kotak_session().status()


@router.post("/session/login")
def session_login(body: LoginBody) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub
    from app.kotak.session import get_kotak_session

    from app.kotak.tick_guard import sanitize_error_text

    try:
        creds = get_kotak_session().login(
            mobile=body.mobile,
            ucc=body.ucc,
            totp=body.totp,
            mpin=body.mpin,
            feed_url=body.feed_url,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=sanitize_error_text(e)
        ) from e
    out: dict[str, Any] = {"ok": True, "session": creds.public_status()}
    if body.start_feed:
        try:
            out["feed"] = get_feed_hub().start(creds)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=sanitize_error_text(e)
            ) from e
    return out


@router.post("/session/logout")
def session_logout() -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub
    from app.kotak.session import get_kotak_session

    get_feed_hub().stop()
    get_kotak_session().clear()
    return {"ok": True}


@router.get("/feed/status")
def feed_status() -> dict[str, Any]:
    """Public feed health — no session secrets; includes provider policy."""
    from app.kotak.feed_hub import get_feed_hub
    from app.providers.live_quote_provider import provider_policy_public

    st = get_feed_hub().status()
    st["provider_policy"] = st.get("provider_policy") or provider_policy_public()
    # Explicit honesty: paths exist in client; live e2e not claimed
    st["coverage_claims"] = {
        "ltp": "protocol_supported_not_live_e2e_verified",
        "depth_l2": "subscribe_path_exists_not_live_e2e_verified",
        "fno": "subscribe_path_exists_not_live_e2e_verified",
        "live_e2e_verified_in_ci": False,
    }
    return st


@router.post("/feed/start")
def feed_start() -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub
    from app.kotak.tick_guard import sanitize_error_text

    try:
        return get_feed_hub().start()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=sanitize_error_text(e)
        ) from e


@router.post("/feed/stop")
def feed_stop() -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    get_feed_hub().stop()
    return {"ok": True}


@router.post("/feed/subscribe")
def feed_subscribe(body: SubscribeBody) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    hub = get_feed_hub()
    keys = []
    errors = []
    for sym in body.symbols:
        try:
            keys.append(
                hub.subscribe_equity(sym, exchange_segment=body.exchange_segment)
            )
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)})
    if not keys and errors:
        raise HTTPException(status_code=400, detail=errors)
    return {"ok": True, "keys": keys, "errors": errors}


@router.post("/feed/subscribe/future")
def feed_subscribe_future(body: FutureBody) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    try:
        key = get_feed_hub().subscribe_future(
            body.underlying, body.expiry, exchange_segment=body.exchange_segment
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "key": key}


@router.post("/feed/subscribe/option")
def feed_subscribe_option(body: OptionBody) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    try:
        key = get_feed_hub().subscribe_option(
            body.underlying,
            body.expiry,
            body.strike,
            body.right,
            exchange_segment=body.exchange_segment,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "key": key}


@router.post("/feed/unsubscribe")
def feed_unsubscribe(body: UnsubscribeBody) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    get_feed_hub().unsubscribe(body.keys)
    return {"ok": True, "keys": body.keys}


@router.get("/feed/quote/{key}")
def feed_quote(key: str) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    q = get_feed_hub().get_quote(key)
    if q is None:
        raise HTTPException(status_code=404, detail=f"No live quote for {key}")
    return q.to_dict()


@router.get("/feed/depth/{key}")
def feed_depth(key: str) -> dict[str, Any]:
    """L2 book when present. Empty books are labeled unavailable — never fake depth."""
    from app.kotak.feed_hub import get_feed_hub

    hub = get_feed_hub()
    book = hub.get_book(key)
    quote = hub.get_quote(key)
    if book is None and quote is None:
        raise HTTPException(status_code=404, detail=f"No depth for {key}")
    if book is None:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "no_l2_book_cached_subscribe_path_not_e2e_verified",
            "key": key,
            "bids": None,
            "asks": None,
            "obi": None,
            "spread_pct": None,
            "ltp": quote.ltp if quote else None,
            "symbol": quote.symbol if quote else None,
        }
    out = book.to_dict()
    bids = out.get("bids") or []
    asks = out.get("asks") or []
    if not bids and not asks:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "l2_book_empty_not_displayed_as_market_data",
            "key": key,
            "bids": None,
            "asks": None,
            "obi": None,
            "spread_pct": None,
            "ltp": quote.ltp if quote else None,
            "symbol": quote.symbol if quote else None,
        }
    out["available"] = True
    out["status"] = "ok"
    out["key"] = key
    if quote:
        out["ltp"] = quote.ltp
        out["symbol"] = quote.symbol
        out["obi"] = quote.obi if quote.obi is not None else out.get("obi")
        out["spread_pct"] = (
            quote.spread_pct if quote.spread_pct is not None else out.get("spread_pct")
        )
    return out


@router.get("/feed/bars/{key}")
def feed_bars(key: str, interval: str = "1m", limit: int = 200) -> dict[str, Any]:
    from app.kotak.feed_hub import get_feed_hub

    try:
        bars = get_feed_hub().get_bars(key, interval=interval, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"key": key, "interval": interval, "bars": bars, "count": len(bars)}


@router.get("/scrip/status")
def scrip_status() -> dict[str, Any]:
    from app.kotak.scrip_master import get_scrip_master

    sm = get_scrip_master()
    sm.ensure_loaded()
    return sm.status()


@router.post("/scrip/refresh")
def scrip_refresh() -> dict[str, Any]:
    from app.kotak.scrip_master import get_scrip_master

    sm = get_scrip_master()
    as_of = sm.ensure_loaded(force=True)
    return {"ok": True, "as_of": as_of, **sm.status()}


@router.get("/scrip/resolve/equity/{symbol}")
def resolve_equity(symbol: str, exchange_segment: str = "nse_cm") -> dict[str, Any]:
    from app.kotak.scrip_master import get_scrip_master

    try:
        inst = get_scrip_master().resolve_equity(symbol, exchange_segment=exchange_segment)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return inst.to_dict()


@router.get("/scrip/resolve/future/{underlying}")
def resolve_future(
    underlying: str,
    expiry: Optional[str] = None,
    exchange_segment: str = "nse_fo",
) -> dict[str, Any]:
    from app.kotak.scrip_master import get_scrip_master

    sm = get_scrip_master()
    try:
        if expiry:
            inst = sm.resolve_future(underlying, expiry, exchange_segment=exchange_segment)
        else:
            inst = sm.nearest_future(underlying, exchange_segment=exchange_segment)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return inst.to_dict()


@router.get("/scrip/resolve/option/{underlying}")
def resolve_option(
    underlying: str,
    expiry: str,
    strike: float,
    right: str,
    exchange_segment: str = "nse_fo",
) -> dict[str, Any]:
    from app.kotak.scrip_master import get_scrip_master

    try:
        inst = get_scrip_master().resolve_option(
            underlying, expiry, strike, right, exchange_segment=exchange_segment
        )
    except (LookupError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return inst.to_dict()


@router.get("/scrip/expiries/{underlying}")
def list_expiries(
    underlying: str, kind: str = "OPT", exchange_segment: str = "nse_fo"
) -> dict[str, Any]:
    from app.kotak.scrip_master import get_scrip_master

    if kind not in ("OPT", "FUT"):
        raise HTTPException(status_code=400, detail="kind must be OPT or FUT")
    exps = get_scrip_master().list_expiries(
        underlying, kind=kind, exchange_segment=exchange_segment  # type: ignore[arg-type]
    )
    return {"underlying": underlying, "kind": kind, "expiries": exps}
