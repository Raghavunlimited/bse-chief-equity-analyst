"""Swing Desk — FastAPI entrypoint (consultant signals + customer platform MVP)."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import config
from app.routers import (
    analyze,
    backtest,
    consultant,
    ingest,
    journal,
    market,
    picks,
    signals,
    stocks,
)
from app.routers import signals_facade
from app.routers import auth as auth_router
from app.routers import admin_platform
from app.routers import platform as platform_router
from app.routers import llm_vault
from app.routers import kotak_feed
from app.routers import option_chain as option_chain_router
from app.routers import trade_ledger as trade_ledger_router
from app.routers import position_sizing as position_sizing_router
from app.routers import market_events as market_events_router
from app.routers import strategy_evaluation as strategy_evaluation_router
from app.security import ApiKeyMiddleware

logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

APP_VERSION = "5.12.5-signal-clarity"

_docs = "/docs" if config.enable_api_docs else None
_redoc = "/redoc" if config.enable_api_docs else None
_openapi = "/openapi.json" if config.enable_api_docs else None

app = FastAPI(
    title="Swing Desk — Trading Analysis & Signals Platform",
    description=(
        "Personal research desks: Swing, Intraday, Index, MCX. "
        "Live adapter only (no demo). EOD vs LTP strictly separated. "
        "Kotak Neo WebSocket L2 + F&O tokens. Walk-forward expectancy gating. "
        "Not investment advice. No trade execution."
    ),
    version=APP_VERSION,
    docs_url=_docs,
    redoc_url=_redoc,
    openapi_url=_openapi,
)

_origins = config.cors_origin_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=("*" not in _origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiKeyMiddleware)

app.include_router(auth_router.router)
app.include_router(platform_router.router)
app.include_router(admin_platform.router)
app.include_router(llm_vault.router)
app.include_router(ingest.router)
app.include_router(picks.router)
app.include_router(journal.router)
app.include_router(backtest.router)
app.include_router(market.router)
app.include_router(stocks.router)
app.include_router(signals.router)
app.include_router(signals_facade.router)
app.include_router(consultant.router)
app.include_router(analyze.router)
app.include_router(kotak_feed.router)
app.include_router(option_chain_router.router)
app.include_router(trade_ledger_router.router)
app.include_router(position_sizing_router.router)
app.include_router(market_events_router.router)
app.include_router(strategy_evaluation_router.router)


@app.on_event("startup")
def _ensure_platform_schema():
    from app.ingest_journal import ensure_journal_schema
    from app.ingest_scheduler import start_scheduler
    from app.ops_security import assert_safe_boot, check_sqlite_schema
    from app.platform_db import PlatformDB
    from app.trade_ledger import ensure_schema as ensure_trade_ledger

    assert_safe_boot()
    PlatformDB(config.db_path)
    ensure_journal_schema(config.db_path)
    ensure_trade_ledger()
    schema = check_sqlite_schema(config.db_path)
    if not schema.get("ok"):
        logging.getLogger(__name__).warning(
            "sqlite_schema_incomplete missing=%s", schema.get("missing_tables")
        )
    else:
        logging.getLogger(__name__).info(
            "sqlite_schema_ok tables=%s", schema.get("present_tables")
        )
    start_scheduler()


@app.get("/json/version")
@app.get("/json/list")
def _chrome_devtools_probe():
    """
    Chrome / Cursor DevTools sometimes probe CDP paths against the API port.
    Return an empty list so logs stay clean (not a real debugger endpoint).
    """
    return []


@app.get("/")
def root():
    return {
        "name": "Swing Desk",
        "version": APP_VERSION,
        "desks": ["swing", "intraday", "index", "mcx"],
        "platform": [
            "/api/auth",
            "/api/platform/signals",
            "/api/market/session",
            "/api/me/llm",
            "/api/admin",
        ],
        "consultant": [
            "/api/consultant/swing",
            "/api/consultant/intraday",
            "/api/consultant/index",
            "/api/consultant/mcx",
        ],
        "analyze": "/api/analyze",
        "docs": "/docs" if config.enable_api_docs else None,
        "auth_enabled": config.auth_enabled,
        "market_data_adapter": config.market_data_adapter,
        "deployment_model": "personal_local_research_desk",
        "production_ready_claim": False,
        "ledger": {
            "path": "/api/ledger/summary",
            "note": "User-entered trade journal — not broker fills; not listed with trade contents here.",
        },
        "position_sizing": {
            "path": "/api/position-sizing/calculate",
            "note": "Research risk sizing only — not an order instruction; does not place trades.",
        },
        "market_events": {
            "path": "/api/market-events",
            "note": "Identifiable-source calendar only — no invented dates/forecasts/impact.",
        },
        "strategy_evaluation": {
            "path": "/api/strategy-evaluation",
            "note": "Research walk-forward / OOS evidence only — does not select a best or proven strategy.",
        },
    }


def _security_public_status() -> dict:
    from app.ops_security import security_posture

    return security_posture()


def _schema_public_status() -> dict:
    from app.ops_security import check_sqlite_schema

    return check_sqlite_schema(config.db_path)


def _kotak_public_status() -> dict:
    from app import kotak_eod

    raw = kotak_eod.status() or {}
    return {
        "configured": bool(raw.get("configured")),
        "consumer_key_present": bool(raw.get("consumer_key_present")),
        "note": raw.get("note"),
    }


def _eod_ingest_public_status() -> dict:
    try:
        from app.ingest_journal import journal_summary
        from app.ingest_scheduler import scheduler_status
        from app.nse_calendar import calendar_public_status

        return {
            "calendar": calendar_public_status(),
            "scheduler": scheduler_status(),
            "journal": journal_summary(),
        }
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {"error": sanitize_error_text(e)}


def _bars_5m_public_status() -> dict:
    try:
        from app.bars_5m import bar_counts

        return {
            **bar_counts(),
            "retention_days": config.bars_5m_retention_days,
            "yahoo_range": config.bars_5m_yahoo_range,
            "note": (
                "Completed 5m bars only (IST session). Used for Intraday/Index "
                "expectancy — not a daily proxy."
            ),
        }
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {"completed_bars": 0, "error": sanitize_error_text(e)}


def _kotak_feed_public_status() -> dict:
    try:
        from app.kotak.feed_hub import get_feed_hub
        from app.kotak.session import get_kotak_session

        sess = get_kotak_session().status()
        hub = get_feed_hub().status()
        return {
            "session_authenticated": bool(sess.get("authenticated")),
            "ws_connected": bool((hub.get("ws") or {}).get("connected")),
            "quotes_cached": hub.get("quotes_cached", 0),
        }
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {
            "session_authenticated": False,
            "ws_connected": False,
            "error": sanitize_error_text(e),
        }


@app.get("/api/health")
def health():
    """Liveness — process is up (does not imply fresh market data or broker LIVE)."""
    from app.market_session import CALENDAR_NOTE, session_snapshot

    return {
        "status": "ok",
        "liveness": True,
        "data_ready": None,
        "version": APP_VERSION,
        "desks": ["swing", "intraday", "index", "mcx"],
        "product": "personal_trading_desk",
        "feeds": {
            "kotak": _kotak_public_status(),
            "live_quotes": {
                "path": "kotak_neo_ws_preferred_else_yahoo_chart",
                "broker_live_source": "kotak_neo_ws",
                "broker_protocol": "native_batch_apifeed_hs",
                "research_fallback_source": "yahoo_chart",
                "yahoo_ltp_fallback_allowed": bool(config.allow_yahoo_ltp_fallback),
                "note": (
                    "Yahoo age-fresh quotes are market_data_state=FALLBACK, "
                    "never provenance=live / broker LIVE. "
                    "Set ALLOW_YAHOO_LTP_FALLBACK=false to fail closed without Yahoo."
                ),
            },
            "kotak_feed": _kotak_feed_public_status(),
            "market_data_adapter": config.market_data_adapter,
            "demo_allowed": False,
            "live_quote_stale_sec": config.live_quote_stale_sec,
            "bars_5m": _bars_5m_public_status(),
        },
        "session": session_snapshot(),
        "calendar_note": CALENDAR_NOTE,
        "eod_ingest": _eod_ingest_public_status(),
        "auth_enabled": config.auth_enabled,
        "auth_required_for_mutations": bool(config.api_key) or config.auth_enabled,
        "security": _security_public_status(),
        "schema": _schema_public_status(),
        # Intentionally omit trade rows / P&L — journal is private personal data
        "ledger_present": True,
        "ledger_note": "Trade journal at /api/ledger/* — contents not embedded in health.",
    }


@app.get("/api/health/ready")
def ready():
    """
    Data readiness — EOD freshness for Swing (not LTP, not process liveness).
    503 when EOD is not FRESH, demo provenance present, or Kotak EOD not configured.
    """
    from app.meta import data_provenance
    from app.store import Database

    db = Database(config.db_path)
    freshness = db.freshness(config.ready_max_data_age_days)
    provenance = data_provenance(config.db_path)
    is_demo = bool(provenance.get("is_demo") or provenance.get("data_source") == "demo")
    kotak = _kotak_public_status()
    status = freshness.get("status")
    ready_ok = (
        status == "FRESH"
        and not is_demo
        and bool(kotak.get("configured"))
        and config.market_data_adapter not in ("demo", "mock")
    )

    if is_demo:
        msg = "DEMO / synthetic EOD detected in DB — Force full with Kotak; demo is forbidden"
    elif not kotak.get("configured"):
        msg = "Kotak consumer key missing — refuse to pretend live EOD is available"
    elif status != "FRESH":
        msg = freshness.get("message") or f"Not ready: {status}"
    else:
        msg = "Ready"

    body = {
        "ready": ready_ok,
        "liveness": True,
        "data_ready": ready_ok,
        "readiness_plane": "eod",
        "version": APP_VERSION,
        "freshness": freshness,
        "provenance": {
            "data_source": provenance.get("data_source"),
            "is_demo": is_demo,
            "data_note": provenance.get("data_note"),
            "market_data_adapter": config.market_data_adapter,
        },
        "allow_demo_data": False,
        "kotak_configured": bool(kotak.get("configured")),
        "message": msg if not ready_ok else "Ready (EOD FRESH)",
        "note": (
            "This endpoint is EOD readiness for Swing. "
            "Intraday/Index LTP health is per-desk feed_health (LIVE vs FALLBACK vs STALE)."
        ),
    }
    if ready_ok:
        return body
    return JSONResponse(body, status_code=503)


@app.get("/api/methodology")
def methodology():
    from app.signals.methodology import METHODOLOGY_DOC

    return METHODOLOGY_DOC
