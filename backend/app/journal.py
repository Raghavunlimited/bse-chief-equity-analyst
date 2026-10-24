"""
Simple trade journal — JSON file under data/.

Research log only; not a broker ledger and not investment advice.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _default_path() -> Path:
    try:
        from app.config import config

        return config.data_dir / "trade_journal.json"
    except Exception:
        # Fallback when config deps (e.g. dotenv) are unavailable
        return Path(__file__).resolve().parent.parent / "data" / "trade_journal.json"


def _path(path: Path | None = None) -> Path:
    p = path or _default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load(path: Path | None = None) -> dict[str, Any]:
    p = _path(path)
    if not p.exists():
        return {"entries": []}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"entries": []}
        entries = data.get("entries")
        if not isinstance(entries, list):
            data["entries"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _save(data: dict[str, Any], path: Path | None = None) -> None:
    p = _path(path)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(p)


def add_entry(
    *,
    week: str,
    symbol: str,
    invested: bool = False,
    capital_deployed: float | None = None,
    pnl_rupees: float | None = None,
    pnl_pct: float | None = None,
    notes: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append a journal entry. Returns the stored record."""
    week = str(week or "").strip()
    symbol = str(symbol or "").strip().upper()
    if not week or not symbol:
        raise ValueError("week and symbol are required")

    entry = {
        "id": str(uuid.uuid4()),
        "week": week,
        "symbol": symbol,
        "invested": bool(invested),
        "capital_deployed": (
            None if capital_deployed is None else round(float(capital_deployed), 2)
        ),
        "pnl_rupees": None if pnl_rupees is None else round(float(pnl_rupees), 2),
        "pnl_pct": None if pnl_pct is None else round(float(pnl_pct), 4),
        "notes": (notes or "").strip() or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Personal research log only — not advice or a guarantee.",
    }

    with _lock:
        data = _load(path)
        entries = data.setdefault("entries", [])
        # Upsert latest row per week+symbol so users can edit P&L
        entries = [
            e
            for e in entries
            if not (
                str(e.get("week") or "") == week
                and str(e.get("symbol") or "").upper() == symbol
            )
        ]
        entries.append(entry)
        data["entries"] = entries
        _save(data, path)
    return entry


def list_entries(
    *,
    week: str | None = None,
    limit: int = 100,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Entries newest-first; optional week filter (ISO label)."""
    with _lock:
        entries = list(_load(path).get("entries") or [])
    if week:
        w = str(week).strip()
        entries = [e for e in entries if str(e.get("week") or "") == w]
    entries.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)
    return entries[: max(1, int(limit))]


def list_weeks(*, limit: int = 26, path: Path | None = None) -> list[dict[str, Any]]:
    """Recent weeks with entry counts, newest first."""
    with _lock:
        entries = list(_load(path).get("entries") or [])

    by_week: dict[str, dict[str, Any]] = {}
    for e in entries:
        w = str(e.get("week") or "").strip()
        if not w:
            continue
        bucket = by_week.setdefault(
            w,
            {
                "week": w,
                "entries": 0,
                "invested": 0,
                "pnl_rupees_sum": 0.0,
                "latest_at": e.get("created_at"),
            },
        )
        bucket["entries"] += 1
        if e.get("invested"):
            bucket["invested"] += 1
        if e.get("pnl_rupees") is not None:
            try:
                bucket["pnl_rupees_sum"] += float(e["pnl_rupees"])
            except (TypeError, ValueError):
                pass
        created = str(e.get("created_at") or "")
        if created > str(bucket.get("latest_at") or ""):
            bucket["latest_at"] = created

    weeks = sorted(
        by_week.values(),
        key=lambda x: str(x.get("latest_at") or x.get("week") or ""),
        reverse=True,
    )
    for w in weeks:
        w["pnl_rupees_sum"] = round(float(w["pnl_rupees_sum"]), 2)
    return weeks[: max(1, int(limit))]
