"""Ingest orchestration with progress reporting."""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import config
from app.features import recompute_and_store
from app.ingest import NSEDataIngester
from app.meta import data_provenance, set_meta
from app.progress import finish_progress, reset_progress, update_progress
from app.store import Database
from app import kotak_eod
from app.universe_nse import build_ingest_universe
from app.yahoo_eod import fetch_nifty, fetch_symbols

logger = logging.getLogger(__name__)


def _try_nse(db: Database, last: Optional[str], max_days: int = 8) -> tuple[int, list, str]:
    update_progress(phase="nse", message="Checking NSE bhavcopy…", current=0, total=max_days)
    ingester = NSEDataIngester(config.cache_dir, config.raw_dir)
    frames = ingester.fill_gap(last, max_days=max_days)
    rows = 0
    dates = []
    for i, df in enumerate(frames):
        rows += db.upsert_eod_data(df)
        if not df.empty:
            dates.append(str(df["trade_date"].iloc[0]))
        update_progress(
            phase="nse",
            message=f"NSE day {i + 1}/{max(len(frames), 1)}…",
            current=i + 1,
            total=max(len(frames), 1),
        )
    return rows, dates, "nse_bhavcopy" if rows else "none"


def run_incremental_ingest(
    db: Optional[Database] = None,
    *,
    force_full: bool = False,
) -> dict[str, Any]:
    reset_progress()
    db = db or Database(config.db_path)
    try:
        last = db.get_max_trade_date()
        freshness = db.freshness(config.max_data_age_days)
        provenance = data_provenance(config.db_path)

        # Fast path when live-ish data already fresh (not for forcing full)
        if (
            not force_full
            and last
            and freshness.get("status") in ("FRESH", "RECENT")
            and provenance.get("data_source") != "demo"
        ):
            update_progress(phase="nifty", message="Refreshing NIFTY…", current=1, total=3)
            nifty = fetch_nifty(range_="3mo")
            nifty_rows = db.upsert_eod_data(nifty) if not nifty.empty else 0
            update_progress(phase="nse", message="Checking for new NSE sessions…", current=2, total=3)
            rows, dates, source = _try_nse(db, last, max_days=3)
            if rows:
                update_progress(phase="indicators", message="Recomputing indicators…", current=3, total=3)
                recompute_and_store(db, lookback_days=120)
                set_meta(config.db_path, "data_source", "nse" if source == "nse_bhavcopy" else "mixed")
            freshness = db.freshness(config.max_data_age_days)
            result = {
                "status": "ok",
                "source": source if rows else "cache",
                "eod_rows": rows,
                "dates_ingested": dates,
                "nifty_rows": nifty_rows,
                "indicator_rows": 0,
                "freshness": freshness,
                "provenance": data_provenance(config.db_path),
                "message": (
                    "Data already fresh — light refresh only. "
                    f"NSE new rows={rows}, NIFTY rows={nifty_rows}."
                ),
            }
            finish_progress(result)
            return result

        update_progress(phase="nse", message="Downloading NSE bhavcopy…", current=0, total=5)
        rows, dates, source = _try_nse(db, last, max_days=8)
        nifty_rows = 0

        need_yahoo = rows == 0 and (
            force_full
            or not last
            or freshness.get("status") in ("EMPTY", "STALE")
            or provenance.get("data_source") == "demo"
        )

        if need_yahoo:
            prefer = db.get_all_symbols()
            symbols = build_ingest_universe(
                max_symbols=config.max_ingest_symbols,
                prefer=prefer,
            )
            n = len(symbols)
            # Kotak daily max ≤180 calendar days (use 179).
            days = 179 if provenance.get("data_source") == "demo" or not last else 120
            broker_ok = False
            pause = float(config.ingest_pause_sec)
            workers = int(config.ingest_workers)

            # 1) Kotak Neo (consumer key — historical works, concurrent)
            if kotak_eod.is_configured():
                source = "kotak"
                update_progress(
                    phase="kotak",
                    message=f"Authenticating Kotak · {n} names · {workers} workers…",
                    current=0,
                    total=n + 1,
                    source="kotak",
                )
                kprobe = kotak_eod.probe()
                if not kprobe.get("ok"):
                    update_progress(
                        phase="kotak",
                        message=f"Kotak blocked — {(kprobe.get('message') or '')[:72]}",
                        current=0,
                        total=n,
                        source="kotak",
                    )
                    set_meta(
                        config.db_path,
                        "data_note",
                        kprobe.get("message") or "Kotak probe failed",
                    )
                else:
                    update_progress(
                        phase="kotak",
                        message="Fetching NIFTY via Kotak…",
                        current=0,
                        total=n + 1,
                        source="kotak",
                    )
                    nifty = kotak_eod.fetch_nifty_daily(days=min(days, 179))
                    if nifty.empty:
                        nifty = fetch_nifty(range_="3mo")
                    nifty_rows = db.upsert_eod_data(nifty) if not nifty.empty else 0

                    def on_kotak(i: int, sym: str, ok: bool):
                        st = "ok" if ok else "failed"
                        update_progress(
                            phase="kotak",
                            message=f"Kotak ×{workers} · {i}/{n} · {sym} ({st})",
                            current=i,
                            total=n,
                            source="kotak",
                        )

                    kdf = kotak_eod.fetch_symbols(
                        symbols,
                        days=min(days, 179),
                        pause=pause,
                        max_symbols=n,
                        on_progress=on_kotak,
                        workers=workers,
                    )
                    if not kdf.empty:
                        rows = db.upsert_eod_data(kdf)
                        max_live = str(kdf["trade_date"].max())
                        # Demo seed often has a fake "today" row sitting above live EOD
                        db.purge_eod_after(max_live)
                        dates = sorted(kdf["trade_date"].unique().tolist())[-10:]
                        set_meta(config.db_path, "data_source", "kotak")
                        set_meta(
                            config.db_path,
                            "data_note",
                            "Live EOD from Kotak Neo historical API.",
                        )
                        broker_ok = True
                    else:
                        set_meta(
                            config.db_path,
                            "data_note",
                            "Kotak probe OK but stock fetch empty (rate limit?). Retry Force full.",
                        )

            # 2) Yahoo fallback
            if not broker_ok:
                source = "yahoo_chart"
                update_progress(
                    phase="yahoo",
                    message="Kotak unavailable — fetching via Yahoo…",
                    current=0,
                    total=n,
                    source="yahoo_chart",
                )
                nifty = fetch_nifty(range_="1y")
                nifty_rows = db.upsert_eod_data(nifty) if not nifty.empty else 0

                def on_symbol(i: int, sym: str, ok: bool):
                    st = "ok" if ok else "failed"
                    update_progress(
                        phase="yahoo",
                        message=f"Yahoo · {i} of {n} · {sym} ({st})",
                        current=i,
                        total=n,
                        source="yahoo_chart",
                    )

                update_progress(
                    phase="yahoo",
                    message=f"Yahoo · 0 of {n}",
                    current=0,
                    total=n,
                    source="yahoo_chart",
                )
                yahoo_df = fetch_symbols(
                    symbols[:80],
                    range_="3mo" if last and provenance.get("data_source") != "demo" else "1y",
                    pause=0.75,
                    max_symbols=80,
                    on_progress=on_symbol,
                )
                if not yahoo_df.empty:
                    rows = db.upsert_eod_data(yahoo_df)
                    dates = sorted(yahoo_df["trade_date"].unique().tolist())[-10:]
                    set_meta(config.db_path, "data_source", "yahoo")
                    set_meta(
                        config.db_path,
                        "data_note",
                        "Yahoo fallback. Prefer Kotak (KOTAK_CONSUMER_KEY).",
                    )
                else:
                    set_meta(
                        config.db_path,
                        "data_note",
                        "All feeds empty — set KOTAK_CONSUMER_KEY.",
                    )
        else:
            update_progress(phase="nifty", message="Refreshing NIFTY…", current=4, total=5)
            nifty = fetch_nifty(range_="1y")
            nifty_rows = db.upsert_eod_data(nifty) if not nifty.empty else 0
            if source == "nse_bhavcopy":
                set_meta(config.db_path, "data_source", "nse")
                set_meta(config.db_path, "data_note", "NSE CM-UDiFF bhavcopy")

        update_progress(phase="indicators", message="Computing indicators…", current=99, total=100)
        ind_rows = recompute_and_store(db, lookback_days=400)
        freshness = db.freshness(config.max_data_age_days)
        result = {
            "status": "ok",
            "source": source,
            "eod_rows": rows,
            "dates_ingested": dates,
            "nifty_rows": nifty_rows,
            "indicator_rows": ind_rows,
            "freshness": freshness,
            "provenance": data_provenance(config.db_path),
            "message": (
                f"Source={source}; {rows} EOD rows, {nifty_rows} NIFTY rows, "
                f"{ind_rows} indicators"
            ),
        }
        finish_progress(result)
        return result
    except Exception as e:
        logger.exception("ingest failed")
        finish_progress(error=str(e))
        raise
