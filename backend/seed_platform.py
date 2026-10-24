#!/usr/bin/env python3
"""Seed demo users, instruments, and auditable demo signals. Idempotent-ish."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SECRET_KEY", "dev-only-change-me-swing-desk-32c")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ALLOW_DEMO_DATA", "true")
os.environ.setdefault("MARKET_DATA_ADAPTER", "demo")

from app.adapters.demo import COMMODITIES, EQUITIES, _SEED  # noqa: E402
from app.auth_deps import hash_password  # noqa: E402
from app.config import config  # noqa: E402
from app.platform_db import PlatformDB  # noqa: E402
from app.signals.methodology import apply_baseline  # noqa: E402


def main() -> None:
    db = PlatformDB(config.db_path)
    print(f"Platform DB: {config.db_path}")

    for email, password, role, name in [
        ("admin@swingdesk.local", "AdminDemo1!", "admin", "Demo Admin"),
        ("customer@swingdesk.local", "Customer1!", "customer", "Demo Customer"),
    ]:
        if db.get_user_by_email(email):
            print(f"  user exists: {email}")
        else:
            db.create_user(email, hash_password(password), role=role, display_name=name)
            print(f"  created {role}: {email} / {password}")

    admin = db.get_user_by_email("admin@swingdesk.local")

    for sym in EQUITIES:
        cat = "intraday" if sym == "INFY" else "swing"
        db.upsert_instrument(sym, cat, name=sym, market="NSE")
    for sym in COMMODITIES:
        db.upsert_instrument(sym, "commodity", name=sym, market="MCX")
    # Extra swing name for insufficient-evidence example
    db.upsert_instrument("SBIN", "swing", name="State Bank of India", market="NSE")
    print(f"  instruments: {len(db.list_instruments(active_only=False))}")

    existing = db.list_signals(include_history=True, limit=5)
    if existing:
        print(f"  signals already present ({len(existing)}+); skip demo publish")
        print("Done. Demo logins: admin@swingdesk.local / AdminDemo1!  |  customer@swingdesk.local / Customer1!")
        return

    samples = [
        ("RELIANCE", "swing", {"close": 2950, "sma_20": 2900, "rsi_14": 58, "volume_ratio": 1.8}),
        ("TCS", "swing", {"close": 4125, "sma_20": 4200, "rsi_14": 42, "volume_ratio": 1.1}),
        ("INFY", "intraday", {"close": 1880, "sma_20": 1850, "rsi_14": 62, "volume_ratio": 2.1}),
        (
            "GOLD",
            "commodity",
            {
                "close": 72500,
                "sma_20": 71800,
                "rsi_14": 55,
                "volume_ratio": 1.6,
                "oi_available": True,
                "oi_change": 120,
            },
        ),
        (
            "CRUDE",
            "commodity",
            {
                "close": 6450,
                "sma_20": 6600,
                "rsi_14": 35,
                "volume_ratio": 1.2,
                "oi_available": True,
                "oi_change": -80,
            },
        ),
        ("SBIN", "swing", {"rsi_14": 50}),
    ]

    expires = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat()
    for sym, cat, evidence in samples:
        graded = apply_baseline(sym, cat, evidence, data_mode="demo")
        db.publish_signal(
            {
                **graded,
                "status": "published",
                "expires_at": expires,
                "provenance": {
                    "data_mode": "demo",
                    "source": "seed_platform",
                    "note": "DEMO seed — not live market data",
                    "as_of": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "seed_last": _SEED.get(sym, {}).get("last"),
                },
            },
            actor_id=admin["id"] if admin else None,
        )
        print(f"  signal {sym}/{cat} → {graded['direction']}")

    old = apply_baseline(
        "SILVER",
        "commodity",
        {
            "close": 87500,
            "sma_20": 86000,
            "rsi_14": 60,
            "volume_ratio": 1.7,
            "oi_available": True,
            "oi_change": 50,
        },
        data_mode="demo",
    )
    past = (datetime.now(timezone.utc) - timedelta(days=3)).replace(microsecond=0).isoformat()
    with db.connect() as conn:
        sid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO signal_records(
              id, symbol, category, direction, timeframe, status,
              created_at, expires_at, published_at, rationale, evidence_json,
              provenance_json, risk_notes, methodology_id, data_mode, created_by, revision
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sid,
                "SILVER",
                "commodity",
                old["direction"],
                old["timeframe"],
                "expired",
                past,
                past,
                past,
                old["rationale"] + " [historical demo]",
                json.dumps(old["evidence"]),
                json.dumps(
                    {
                        "data_mode": "demo",
                        "source": "seed_platform",
                        "note": "Expired DEMO record",
                    }
                ),
                old["risk_notes"],
                old["methodology_id"],
                "demo",
                admin["id"] if admin else None,
                1,
            ),
        )
        conn.commit()
    print("  historical expired SILVER demo signal added")
    print(
        "Done. Demo logins: admin@swingdesk.local / AdminDemo1!  |  customer@swingdesk.local / Customer1!"
    )


if __name__ == "__main__":
    main()
