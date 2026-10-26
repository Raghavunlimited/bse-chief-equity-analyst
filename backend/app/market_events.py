"""
Market events calendar — identifiable sources only.

Shows scheduled facts and reported outcomes from operator-maintained snapshots
(and optional verified broker scrip-master expiries). Does **not** invent dates,
forecasts, outcomes, or market impact. Model commentary is never emitted as fact.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.nse_calendar import clear_calendar_cache, holidays_file_path, load_holiday_dates

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

DISCLAIMER = (
    "Market events from identifiable operator/broker snapshots only — "
    "not a live economic calendar scrape. No invented dates, forecasts, "
    "outcomes, or market impact. Scheduled facts and reported outcomes are "
    "labeled separately from any model commentary (none invented here)."
)

CONTENT_KINDS = frozenset({"scheduled_fact", "reported_outcome"})
# Explicitly never treat as primary fact without a separate labeled channel:
MODEL_COMMENTARY_KIND = "model_commentary"

_DEFAULT_EVENTS_FILE = Path(__file__).resolve().parent / "data" / "market_events.json"
_DEFAULT_HOLIDAY_STALE_DAYS = 120
_DEFAULT_EVENTS_STALE_DAYS = 45


def _events_file_path() -> Path:
    from app.config import config

    raw = getattr(config, "market_events_file", None) or ""
    raw = str(raw).strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (Path(__file__).resolve().parent.parent / p)
    return _DEFAULT_EVENTS_FILE


def _parse_dt(raw: Any, *, default_tz: ZoneInfo = IST) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            return dt.replace(tzinfo=default_tz)
        return dt
    s = str(raw).strip()
    if not s:
        return None
    # date-only → start of day in default_tz
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        d = date.fromisoformat(s)
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=default_tz)
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt


def to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def to_tz_iso(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).isoformat()


def _stable_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"ev_{h}"


def _feed_status(
    *,
    present: bool,
    as_of: Optional[str],
    last_updated: Optional[datetime],
    stale_after_days: int,
    now: datetime,
    missing_reason: str,
) -> dict[str, Any]:
    if not present:
        return {
            "status": "unavailable",
            "stale": False,
            "is_current": False,
            "presented_as_current": False,
            "reason": missing_reason,
            "as_of": as_of,
            "last_updated": None,
            "stale_after_days": stale_after_days,
        }
    ref = last_updated
    if ref is None and as_of:
        ref = _parse_dt(as_of)
    age_days: Optional[float] = None
    stale = False
    reason = "ok"
    if ref is not None:
        age_days = max(0.0, (now - ref.astimezone(UTC)).total_seconds() / 86400.0)
        if age_days > float(stale_after_days):
            stale = True
            reason = (
                f"Feed last_updated/as_of is {age_days:.0f}d old "
                f"(stale_after_days={stale_after_days}). "
                "STALE — not a current calendar. Refresh from the NSE cash-market "
                "holiday circular before treating dates as current."
            )
    else:
        stale = True
        reason = (
            "Feed present but as_of/last_updated missing — treated as stale. "
            "STALE — not a current calendar."
        )
    status = "stale" if stale else "fresh"
    return {
        "status": status,
        "stale": stale,
        # Only a fresh snapshot may be presented as current
        "is_current": status == "fresh",
        "presented_as_current": False if stale else True,
        "reason": reason,
        "as_of": as_of,
        "last_updated": to_utc_iso(ref) if ref else None,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "stale_after_days": stale_after_days,
    }


def _normalize_event(
    *,
    event_id: str,
    title: str,
    category: str,
    content_kind: str,
    event_dt: datetime,
    tz_name: str,
    status: str,
    source: dict[str, Any],
    feed_status: str,
    outcome: Optional[dict[str, Any]] = None,
    source_note: Optional[str] = None,
    changed: bool = False,
    previous: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    kind = content_kind if content_kind in CONTENT_KINDS else "scheduled_fact"
    tz = ZoneInfo(tz_name) if tz_name else IST
    out: dict[str, Any] = {
        "id": event_id,
        "title": title,
        "category": category,
        "content_kind": kind,
        "content_kind_label": (
            "Scheduled fact"
            if kind == "scheduled_fact"
            else "Reported outcome"
        ),
        "event_time_utc": to_utc_iso(event_dt),
        "event_time_local": to_tz_iso(event_dt, tz),
        "timezone": tz_name or "Asia/Kolkata",
        "status": status,
        "feed_status": feed_status,
        # Stale / unavailable snapshots must never read as a current calendar
        "presented_as_current": feed_status == "fresh",
        "is_current": feed_status == "fresh",
        "source": source,
        "source_note": source_note,
        "outcome": outcome,
        "model_commentary": None,
        "model_commentary_note": (
            "No model-generated commentary is attached. "
            "Any future commentary would be labeled separately from facts/outcomes."
        ),
        "changed": changed,
        "previous": previous,
        "invented": False,
    }
    return out


def load_nse_holiday_events(
    *,
    now: Optional[datetime] = None,
    path: Optional[Path] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = now.astimezone(UTC) if now else datetime.now(UTC)
    p = path or holidays_file_path()
    present = p.is_file()
    holidays, meta = load_holiday_dates(path=p)
    # Re-read raw for names
    raw: dict[str, Any] = {}
    if present:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("nse_holidays read failed: %s", e)
            present = False
            raw = {}

    last_updated = _parse_dt(raw.get("last_updated") or raw.get("as_of"))
    stale_after = int(raw.get("stale_after_days") or _DEFAULT_HOLIDAY_STALE_DAYS)
    feed = _feed_status(
        present=present and meta.complete,
        as_of=meta.as_of,
        last_updated=last_updated,
        stale_after_days=stale_after,
        now=now,
        missing_reason=(
            "NSE holiday snapshot missing or empty — weekday holidays unavailable; "
            "weekends still closed via session clock. Not inventing holiday dates."
        ),
    )
    if feed.get("stale"):
        feed["reason"] = (
            "The desk operator updates nse_holidays.json from the NSE cash-market "
            "holiday circular (no live download). An old as_of marks this holiday "
            "source STALE on purpose — not a current calendar. Leave as_of unchanged "
            "until the circular is operator-verified. "
            + str(feed.get("reason") or "")
        )
        feed["is_current"] = False
        feed["presented_as_current"] = False
    source_block = {
        "id": "nse_holidays_snapshot",
        "label": "NSE cash holiday snapshot (operator-maintained)",
        "url": None,
        "license": (
            "Public NSE holiday circular facts compiled by the operator. "
            "Not an official NSE API feed; not licensed as a redistributable calendar product."
        ),
        "as_of": meta.as_of,
        "last_updated": feed.get("last_updated"),
        "path": meta.path,
        "limitation": meta.limitation,
        "is_current": bool(feed.get("is_current")),
        "presented_as_current": bool(feed.get("presented_as_current")),
    }
    feed_meta = {
        "source_id": source_block["id"],
        "source": source_block,
        "feed": feed,
        "license": source_block["license"],
    }
    if feed["status"] == "unavailable":
        return [], feed_meta

    tz_name = str(raw.get("timezone") or "Asia/Kolkata")
    name_by_date: dict[str, str] = {}
    for item in raw.get("holidays") or []:
        if isinstance(item, dict) and item.get("date"):
            name_by_date[str(item["date"])[:10]] = str(
                item.get("name") or "NSE holiday"
            )
        elif isinstance(item, str):
            name_by_date[item[:10]] = "NSE holiday"

    events: list[dict[str, Any]] = []
    for d in sorted(holidays):
        key = d.isoformat()
        title = name_by_date.get(key, "NSE holiday")
        # All-day market closure — represent as 00:00 IST
        event_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
        today_ist = now.astimezone(IST).date()
        status = "occurred" if d < today_ist else ("scheduled" if d > today_ist else "scheduled")
        if d == today_ist:
            status = "scheduled"
        tentative = "tentative" in title.lower()
        if tentative:
            status = "tentative"
        events.append(
            _normalize_event(
                event_id=_stable_id("nse_holiday", key, title),
                title=title,
                category="nse_holiday",
                content_kind="scheduled_fact",
                event_dt=event_dt,
                tz_name=tz_name,
                status=status,
                source=source_block,
                feed_status=feed["status"],
                source_note=str(raw.get("source_note") or meta.limitation),
            )
        )
    return events, feed_meta


def load_operator_events(
    *,
    now: Optional[datetime] = None,
    path: Optional[Path] = None,
    prior_by_id: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = now.astimezone(UTC) if now else datetime.now(UTC)
    p = path or _events_file_path()
    present = p.is_file()
    raw: dict[str, Any] = {}
    if present:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("market_events read failed: %s", e)
            present = False

    last_updated = _parse_dt(raw.get("last_updated") or raw.get("as_of"))
    stale_after = int(raw.get("stale_after_days") or _DEFAULT_EVENTS_STALE_DAYS)
    feed = _feed_status(
        present=present,
        as_of=raw.get("as_of"),
        last_updated=last_updated,
        stale_after_days=stale_after,
        now=now,
        missing_reason=(
            "Operator market_events.json missing — macro/other events unavailable. "
            "Not inventing dates from third-party calendars."
        ),
    )
    source_block = {
        "id": str(raw.get("source_id") or "operator_market_events"),
        "label": str(raw.get("source_label") or "Operator market events"),
        "url": raw.get("source_url"),
        "license": str(
            raw.get("license")
            or raw.get("license_note")
            or "Operator-compiled; no third-party calendar license claimed."
        ),
        "as_of": raw.get("as_of"),
        "last_updated": feed.get("last_updated"),
        "path": str(p),
        "limitation": raw.get("limitation"),
    }
    feed_meta = {
        "source_id": source_block["id"],
        "source": source_block,
        "feed": feed,
        "license": source_block["license"],
        "license_note": raw.get("license_note"),
    }
    if not present:
        return [], feed_meta

    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw.get("events") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        event_dt = _parse_dt(
            item.get("event_time") or item.get("event_time_local"),
            default_tz=ZoneInfo(str(item.get("timezone") or raw.get("timezone") or "Asia/Kolkata")),
        )
        if not title or event_dt is None:
            # Refuse incomplete rows — do not invent
            continue
        kind = str(item.get("content_kind") or "scheduled_fact").strip()
        if kind == MODEL_COMMENTARY_KIND:
            # Never promote model commentary into the facts calendar
            continue
        if kind not in CONTENT_KINDS:
            kind = "scheduled_fact"
        eid = str(item.get("id") or "").strip() or _stable_id(
            "op", title, to_utc_iso(event_dt)
        )
        if eid in seen_ids:
            # Duplicate id in same feed — keep first, skip later
            continue
        seen_ids.add(eid)

        outcome = None
        if kind == "reported_outcome" or item.get("outcome"):
            oc = item.get("outcome") if isinstance(item.get("outcome"), dict) else {}
            # Do not invent outcome values — only pass through if present
            outcome = {
                "summary": oc.get("summary"),
                "value": oc.get("value"),
                "reported_at": oc.get("reported_at"),
                "kind": "reported_outcome",
            }

        tz_name = str(item.get("timezone") or raw.get("timezone") or "Asia/Kolkata")
        status = str(item.get("status") or "scheduled")
        row_source = {
            **source_block,
            "url": item.get("source_url") or source_block.get("url"),
        }
        prev = (prior_by_id or {}).get(eid)
        changed = False
        previous_snap = None
        if prev:
            if (
                prev.get("event_time_utc") != to_utc_iso(event_dt)
                or prev.get("title") != title
                or prev.get("status") != status
            ):
                changed = True
                previous_snap = {
                    "title": prev.get("title"),
                    "event_time_utc": prev.get("event_time_utc"),
                    "status": prev.get("status"),
                }

        events.append(
            _normalize_event(
                event_id=eid,
                title=title,
                category=str(item.get("category") or "operator"),
                content_kind=kind,
                event_dt=event_dt,
                tz_name=tz_name,
                status=status,
                source=row_source,
                feed_status=feed["status"],
                outcome=outcome,
                source_note=item.get("source_note") or raw.get("limitation"),
                changed=changed,
                previous=previous_snap,
            )
        )
    return events, feed_meta


def load_fo_expiry_events(
    *,
    now: Optional[datetime] = None,
    underlyings: Optional[list[str]] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Optional F&O expiry dates from Kotak scrip master cache when available.
    If cache/session unavailable → feed unavailable (no invented expiry dates).
    """
    now = now.astimezone(UTC) if now else datetime.now(UTC)
    underlyings = underlyings or ["NIFTY", "BANKNIFTY"]
    source_block = {
        "id": "kotak_scrip_master",
        "label": "Kotak Neo scrip master (cached)",
        "url": "https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod",
        "license": (
            "Instrument metadata from Kotak public scrip-master CSVs for personal "
            "broker research use via the desk's existing adapter. Not a redistributable "
            "market-events product; expiry dates only when cache is present and decoded."
        ),
        "as_of": None,
        "last_updated": None,
    }
    try:
        from app.kotak.scrip_master import get_scrip_master

        sm = get_scrip_master()
        # Prefer in-memory / disk cache without forcing network in tests
        instruments = []
        status = {}
        if hasattr(sm, "status"):
            status = sm.status() or {}
        if hasattr(sm, "list_expiries"):
            pass
        cached = bool(status.get("cached") or status.get("nse_fo_rows") or status.get("ready"))
        if not cached and hasattr(sm, "_cache_dir"):
            cached = False
        # Try to read expiries via public API if present
        expiries_map: dict[str, list[date]] = {}
        if hasattr(sm, "expiries_for_underlying"):
            for u in underlyings:
                try:
                    expiries_map[u] = list(sm.expiries_for_underlying(u) or [])
                except Exception:  # noqa: BLE001
                    expiries_map[u] = []
        elif hasattr(sm, "list_instruments"):
            try:
                instruments = sm.list_instruments(segment="nse_fo") or []
            except Exception:  # noqa: BLE001
                instruments = []
            for inst in instruments:
                und = getattr(inst, "underlying", None) or (inst.get("underlying") if isinstance(inst, dict) else None)
                exp = getattr(inst, "expiry", None) or (inst.get("expiry") if isinstance(inst, dict) else None)
                if und in underlyings and exp:
                    if isinstance(exp, str):
                        try:
                            exp = date.fromisoformat(exp[:10])
                        except ValueError:
                            continue
                    expiries_map.setdefault(str(und), [])
                    if exp not in expiries_map[str(und)]:
                        expiries_map[str(und)].append(exp)
        else:
            # Probe cache files only — do not invent
            expiries_map = {}

        has_any = any(expiries_map.values())
        feed = _feed_status(
            present=has_any,
            as_of=status.get("as_of") or status.get("downloaded_at"),
            last_updated=_parse_dt(status.get("downloaded_at") or status.get("as_of")),
            stale_after_days=7,
            now=now,
            missing_reason=(
                "Kotak scrip master expiries unavailable in cache — "
                "F&O expiry events not shown. Not inventing expiry dates."
            ),
        )
        source_block["as_of"] = feed.get("as_of")
        source_block["last_updated"] = feed.get("last_updated")
        feed_meta = {
            "source_id": source_block["id"],
            "source": source_block,
            "feed": feed,
            "license": source_block["license"],
        }
        if not has_any:
            return [], feed_meta

        events: list[dict[str, Any]] = []
        today_ist = now.astimezone(IST).date()
        for und, dates in expiries_map.items():
            for d in sorted(set(dates)):
                if d < today_ist - timedelta(days=7):
                    continue
                if d > today_ist + timedelta(days=120):
                    continue
                event_dt = datetime(d.year, d.month, d.day, 15, 30, 0, tzinfo=IST)
                status_s = "occurred" if d < today_ist else "scheduled"
                events.append(
                    _normalize_event(
                        event_id=_stable_id("fo_expiry", und, d.isoformat()),
                        title=f"{und} F&O expiry",
                        category="fo_expiry",
                        content_kind="scheduled_fact",
                        event_dt=event_dt,
                        tz_name="Asia/Kolkata",
                        status=status_s,
                        source=source_block,
                        feed_status=feed["status"],
                        source_note="Expiry from Kotak scrip master decode — verify with exchange circular.",
                    )
                )
        return events, feed_meta
    except Exception as e:  # noqa: BLE001
        feed = _feed_status(
            present=False,
            as_of=None,
            last_updated=None,
            stale_after_days=7,
            now=now,
            missing_reason=f"F&O expiry feed unavailable ({type(e).__name__}). Not inventing dates.",
        )
        return [], {
            "source_id": source_block["id"],
            "source": source_block,
            "feed": feed,
            "license": source_block["license"],
        }


def merge_events(
    groups: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Merge event lists. Same id → keep latest, mark changed if fields differ.
    Same title+utc time+category from different sources → keep both (distinct sources).
    """
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for group in groups:
        for ev in group:
            eid = ev["id"]
            if eid in by_id:
                prev = by_id[eid]
                if (
                    prev.get("event_time_utc") != ev.get("event_time_utc")
                    or prev.get("title") != ev.get("title")
                    or prev.get("status") != ev.get("status")
                ):
                    ev = {
                        **ev,
                        "changed": True,
                        "previous": {
                            "title": prev.get("title"),
                            "event_time_utc": prev.get("event_time_utc"),
                            "status": prev.get("status"),
                        },
                    }
                by_id[eid] = ev
            else:
                by_id[eid] = ev
                order.append(eid)
    out = [by_id[i] for i in order]
    out.sort(key=lambda e: e.get("event_time_utc") or "")
    return out


def build_calendar(
    *,
    now: Optional[datetime] = None,
    holidays_path: Optional[Path] = None,
    events_path: Optional[Path] = None,
    include_fo: bool = True,
    prior_events: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    now = now.astimezone(UTC) if now else datetime.now(UTC)
    prior_by_id = {e["id"]: e for e in (prior_events or []) if e.get("id")}

    nse_events, nse_feed = load_nse_holiday_events(now=now, path=holidays_path)
    op_events, op_feed = load_operator_events(
        now=now, path=events_path, prior_by_id=prior_by_id
    )
    fo_events: list[dict[str, Any]] = []
    fo_feed: dict[str, Any]
    if include_fo:
        fo_events, fo_feed = load_fo_expiry_events(now=now)
    else:
        fo_feed = {
            "source_id": "kotak_scrip_master",
            "feed": {
                "status": "unavailable",
                "stale": False,
                "reason": "F&O expiry feed skipped for this request.",
            },
            "license": None,
            "source": {"id": "kotak_scrip_master", "label": "Kotak scrip master"},
        }

    events = merge_events([nse_events, op_events, fo_events])
    feeds = [nse_feed, op_feed, fo_feed]
    any_fresh = any(f.get("feed", {}).get("status") == "fresh" for f in feeds)
    any_stale = any(f.get("feed", {}).get("stale") for f in feeds)
    all_unavail = all(f.get("feed", {}).get("status") == "unavailable" for f in feeds)

    return {
        "status": "ok",
        "available": not all_unavail,
        "disclaimer": DISCLAIMER,
        "generated_at_utc": to_utc_iso(now),
        "timezone_default": "Asia/Kolkata",
        "feeds": feeds,
        "feeds_summary": {
            "any_fresh": any_fresh,
            "any_stale": any_stale,
            "all_unavailable": all_unavail,
            # Stale holiday (or other) feeds must not be treated as current
            "any_presented_as_current": any_fresh,
            "stale_not_current": any_stale,
        },
        "count": len(events),
        "events": events,
        "honesty": {
            "invents_dates": False,
            "invents_forecasts": False,
            "invents_outcomes": False,
            "invents_market_impact": False,
            "model_commentary_as_fact": False,
            "third_party_calendar_scrape": False,
        },
        "licensing": {
            "note": (
                "No commercial economic-calendar license is used. "
                "NSE holidays and operator rows are personal research snapshots; "
                "Kotak scrip master is broker instrument metadata when cached."
            ),
            "feeds": [
                {
                    "source_id": f.get("source_id"),
                    "license": f.get("license") or (f.get("source") or {}).get("license"),
                    "feed_status": (f.get("feed") or {}).get("status"),
                }
                for f in feeds
            ],
        },
    }


def clear_caches() -> None:
    clear_calendar_cache()
