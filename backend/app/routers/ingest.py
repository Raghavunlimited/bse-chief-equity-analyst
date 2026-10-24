from __future__ import annotations

import threading

from fastapi import APIRouter, Query

from app.config import config
from app.meta import data_provenance
from app.pipeline import run_incremental_ingest
from app.progress import get_progress
from app.store import Database

router = APIRouter(prefix="/api", tags=["ingest"])
db = Database(config.db_path)
_ingest_lock = threading.Lock()


def _run_ingest(force_full: bool):
    if not _ingest_lock.acquire(blocking=False):
        return
    try:
        # Fresh DB handle in this thread — avoids locking the request worker
        run_incremental_ingest(Database(config.db_path), force_full=force_full)
    finally:
        _ingest_lock.release()


@router.post("/ingest/latest")
def ingest_latest(
    force: bool = Query(False, description="Force full Kotak re-download"),
    wait: bool = Query(False, description="Block until complete (legacy)"),
):
    """
    Start a data refresh.
    Default: runs in a daemon thread — poll GET /api/ingest/progress for %.
    Pass wait=true to block (old behaviour).
    """
    prog = get_progress()
    if prog.get("running") or _ingest_lock.locked():
        return {"status": "busy", "message": "Refresh already running", "progress": prog}

    if wait:
        return run_incremental_ingest(db, force_full=force)

    # BackgroundTasks can block the uvicorn worker on long sync jobs; use a thread.
    t = threading.Thread(target=_run_ingest, args=(force,), daemon=True, name="swing-ingest")
    t.start()
    return {
        "status": "started",
        "message": "Refresh started — poll /api/ingest/progress",
        "progress": get_progress(),
    }


@router.get("/ingest/progress")
def ingest_progress():
    return get_progress()


@router.get("/ingest/status")
def ingest_status():
    from app import kotak_eod

    return {
        "freshness": db.freshness(config.max_data_age_days),
        "stats": db.stats_overview(),
        "provenance": data_provenance(config.db_path),
        "progress": get_progress(),
        "feeds": {"kotak": kotak_eod.status()},
    }


@router.get("/feeds/kotak")
def kotak_feed_status():
    from app import kotak_eod

    return kotak_eod.status()


@router.post("/feeds/kotak/test")
def kotak_feed_test():
    """Probe Kotak Neo consumer key + RELIANCE daily candles."""
    from app import kotak_eod

    return kotak_eod.probe()


@router.get("/stats")
@router.get("/stats/overview")
def stats():
    overview = db.stats_overview()
    overview["ingest_cap"] = config.max_ingest_symbols
    overview["top_n"] = config.top_n
    return {
        **overview,
        "freshness": db.freshness(config.max_data_age_days),
        "provenance": data_provenance(config.db_path),
    }
