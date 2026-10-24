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
from app.security import ApiKeyMiddleware

logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

APP_VERSION = "4.0.0"

_docs = "/docs" if config.enable_api_docs else None
_redoc = "/redoc" if config.enable_api_docs else None
_openapi = "/openapi.json" if config.enable_api_docs else None

app = FastAPI(
    title="Swing Desk — Trading Analysis & Signals Platform",
    description=(
        "Customer research desks: Swing (weekly), Intraday (daily), Commodities. "
        "Auditable signals, optional encrypted BYO-LLM keys, demo vs live labeling. "
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


@app.on_event("startup")
def _ensure_platform_schema():
    from app.platform_db import PlatformDB

    PlatformDB(config.db_path)


@app.get("/")
def root():
    return {
        "name": "Swing Desk",
        "version": APP_VERSION,
        "desks": ["swing", "intraday", "mcx"],
        "platform": [
            "/api/auth",
            "/api/platform/signals",
            "/api/platform/demo/signals",
            "/api/me/llm",
            "/api/admin",
        ],
        "consultant": [
            "/api/consultant/swing",
            "/api/consultant/intraday",
            "/api/consultant/mcx",
        ],
        "analyze": "/api/analyze",
        "docs": "/docs" if config.enable_api_docs else None,
        "auth_enabled": config.auth_enabled,
        "market_data_adapter": config.market_data_adapter,
    }


def _kotak_public_status() -> dict:
    from app import kotak_eod

    raw = kotak_eod.status() or {}
    return {
        "configured": bool(raw.get("configured")),
        "consumer_key_present": bool(raw.get("consumer_key_present")),
        "note": raw.get("note"),
    }


@app.get("/api/health")
def health():
    """Liveness — process is up (does not imply fresh market data)."""
    return {
        "status": "ok",
        "version": APP_VERSION,
        "desks": ["swing", "intraday", "mcx"],
        "product": "customer_signals_platform",
        "feeds": {
            "kotak": _kotak_public_status(),
            "live_quotes": "yahoo_chart_5m",
            "market_data_adapter": config.market_data_adapter,
        },
        "auth_enabled": config.auth_enabled,
        "auth_required_for_mutations": bool(config.api_key) or config.auth_enabled,
    }


@app.get("/api/health/ready")
def ready():
    """Readiness — EOD freshness + optional anti-demo gate."""
    from app.meta import data_provenance
    from app.store import Database

    db = Database(config.db_path)
    freshness = db.freshness(config.ready_max_data_age_days)
    provenance = data_provenance(config.db_path)
    is_demo = bool(provenance.get("is_demo") or provenance.get("data_source") == "demo")
    # When using platform demo adapter, readiness may still pass for local MVP
    status = freshness.get("status")
    ready_ok = status == "FRESH" and (config.allow_demo_data or not is_demo)

    body = {
        "ready": ready_ok,
        "version": APP_VERSION,
        "freshness": freshness,
        "provenance": {
            "data_source": provenance.get("data_source"),
            "is_demo": is_demo,
            "data_note": provenance.get("data_note"),
            "market_data_adapter": config.market_data_adapter,
        },
        "allow_demo_data": config.allow_demo_data,
        "message": (
            "Ready"
            if ready_ok
            else (
                "DEMO data blocked (ALLOW_DEMO_DATA=false)"
                if is_demo and not config.allow_demo_data
                else freshness.get("message") or f"Not ready: {status}"
            )
        ),
    }
    if ready_ok:
        return body
    return JSONResponse(body, status_code=503)


@app.get("/api/methodology")
def methodology():
    from app.signals.methodology import METHODOLOGY_DOC

    return METHODOLOGY_DOC
