"""Application configuration — loads from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = BASE_DIR / "nse_cache"


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


def _path(key: str, default: Path) -> Path:
    raw = os.getenv(key)
    if not raw:
        return default
    p = Path(raw)
    return p if p.is_absolute() else BASE_DIR / p


@dataclass
class Config:
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    raw_dir: Path = RAW_DIR
    cache_dir: Path = CACHE_DIR
    db_path: Path = _path("DATABASE_PATH", DATA_DIR / "swing_trader.db")

    # Risk / universe
    risk_per_trade: float = _float("RISK_PER_TRADE", 0.02)
    min_traded_value: float = _float("MIN_TRADED_VALUE", 10_00_00_000)  # 10 Cr
    min_price: float = _float("MIN_PRICE", 100.0)

    # Strategy (elite_momentum pack)
    min_score: float = _float("MIN_SCORE", 65.0)
    volume_multiplier: float = _float("VOLUME_MULTIPLIER", 2.0)
    rsi_min: float = _float("RSI_MIN", 45.0)
    rsi_max: float = _float("RSI_MAX", 75.0)  # constructive momentum; >75 = overextended
    rs_min_outperformance: float = _float("RS_MIN", 3.0)
    top_n: int = int(os.getenv("TOP_N", "5"))
    max_positions: int = int(os.getenv("MAX_POSITIONS", os.getenv("TOP_N", "5")))
    entry_style: str = os.getenv("ENTRY_STYLE", "breakout")  # breakout | pullback
    default_capital: float = _float("DEFAULT_CAPITAL", 100_000)
    max_hold_days: int = int(os.getenv("MAX_HOLD_DAYS", "5"))
    round_trip_cost: float = _float("ROUND_TRIP_COST", 0.0015)  # ~0.15%

    # Freshness: max age of latest EOD in *trading* days before STALE
    max_data_age_days: int = int(os.getenv("MAX_DATA_AGE_DAYS", "3"))
    # Phase 4 — holiday calendar + scheduled EOD
    nse_holidays_file: str = os.getenv("NSE_HOLIDAYS_FILE", "").strip()
    market_events_file: str = os.getenv("MARKET_EVENTS_FILE", "").strip()
    eod_settle_hour_ist: int = int(os.getenv("EOD_SETTLE_HOUR_IST", "18"))
    eod_settle_minute_ist: int = int(os.getenv("EOD_SETTLE_MINUTE_IST", "30"))
    eod_ingest_schedule_enabled: bool = os.getenv(
        "EOD_INGEST_SCHEDULE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    eod_ingest_hour_ist: int = int(os.getenv("EOD_INGEST_HOUR_IST", "18"))
    eod_ingest_minute_ist: int = int(os.getenv("EOD_INGEST_MINUTE_IST", "45"))
    eod_ingest_poll_sec: int = int(os.getenv("EOD_INGEST_POLL_SEC", "60"))

    # Kotak EOD refresh size. 0 or negative = ALL NSE EQ cash names (~2.5k).
    # Browse/search always cover the full listed EQ universe; this only caps candle ingest.
    # Full ingest is slow (hours) — raise INGEST_WORKERS carefully (max 8).
    max_ingest_symbols: int = int(os.getenv("MAX_INGEST_SYMBOLS", "0"))
    ingest_pause_sec: float = _float("INGEST_PAUSE_SEC", 0.12)
    # Parallel Kotak historical workers (hard-capped at 8 to avoid 429 storms)
    ingest_workers: int = min(8, max(1, int(os.getenv("INGEST_WORKERS", "4"))))

    # Production / readiness (see docs/OPS.md, docs/CTO_READINESS.md)
    cors_origins: str = os.getenv("CORS_ORIGINS", "")
    api_key: str = os.getenv("API_KEY", "").strip()
    # Phase 1: demo permanently disabled. Env ALLOW_DEMO_DATA is ignored if true.
    allow_demo_data: bool = False
    enable_api_docs: bool = os.getenv("ENABLE_API_DOCS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    ready_max_data_age_days: int = int(
        os.getenv("READY_MAX_DATA_AGE_DAYS", os.getenv("MAX_DATA_AGE_DAYS", "3"))
    )

    # Personal desk default: auth OFF (single operator). SaaS login is opt-in.
    auth_enabled: bool = os.getenv("AUTH_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    secret_key: str = os.getenv(
        "SECRET_KEY", "dev-only-change-me-swing-desk-32c"
    ).strip()
    session_ttl_hours: int = int(os.getenv("SESSION_TTL_HOURS", "72"))
    # Phase 7 — bind / exposure (start.sh exports BIND_HOST; uvicorn reads it)
    bind_host: str = (
        os.getenv("BIND_HOST", os.getenv("UVICORN_HOST", "127.0.0.1")).strip()
        or "127.0.0.1"
    )
    # Explicit opt-in to listen on 0.0.0.0 / non-loopback while AUTH is off
    allow_public_bind: bool = os.getenv("ALLOW_PUBLIC_BIND", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    # live only — demo/mock forbidden
    market_data_adapter: str = os.getenv("MARKET_DATA_ADAPTER", "live").strip().lower()
    # LTP older than this during regular hours → STALE + halt live calls
    live_quote_stale_sec: float = _float("LIVE_QUOTE_STALE_SEC", 5.0)
    # When Kotak WS has no quote: allow Yahoo 5m research FALLBACK (never broker LIVE).
    # Set false to fail closed with UNAVAILABLE instead of Yahoo.
    allow_yahoo_ltp_fallback: bool = os.getenv(
        "ALLOW_YAHOO_LTP_FALLBACK", "true"
    ).lower() in ("1", "true", "yes")
    # Phase 3 — persistent 5m bars
    bars_5m_retention_days: int = int(os.getenv("BARS_5M_RETENTION_DAYS", "45"))
    bars_5m_yahoo_range: str = os.getenv("BARS_5M_YAHOO_RANGE", "5d").strip() or "5d"
    # Jurisdiction label shown in disclosures (not a compliance claim)
    jurisdiction_note: str = os.getenv(
        "JURISDICTION_NOTE",
        "Research tooling only. Not registered investment advice in any jurisdiction.",
    )

    def cors_origin_list(self) -> list[str]:
        """Phase 7: never default to ``*`` for auth-off personal desk."""
        raw = (self.cors_origins or "").strip()
        if raw:
            return [o.strip() for o in raw.split(",") if o.strip()]
        # Local CRA (proxy + direct) — explicit localhost only
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]

    def __post_init__(self):
        for dir_path in [self.data_dir, self.raw_dir, self.cache_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        # Phase 1: never allow demo adapter / demo data flag
        object.__setattr__(self, "allow_demo_data", False)
        if self.market_data_adapter in ("demo", "mock", "synthetic", "fake"):
            raise RuntimeError(
                f"MARKET_DATA_ADAPTER={self.market_data_adapter!r} forbidden. "
                "Set MARKET_DATA_ADAPTER=live in backend/.env"
            )


config = Config()
