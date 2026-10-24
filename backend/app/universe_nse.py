"""
Liquid NSE equity universe from Kotak public scrip master.

This desk screens NSE cash equities (not the full BSE board). Full exchange
listings include illiquid / SME / ETF names that are unsuitable for weekly swings.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import requests

from app.yahoo_eod import CORE_UNIVERSE

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "kotak_cache"

# Skip ETF / index wrappers / bonds noise in symbol names
_SKIP_RE = re.compile(
    r"(ETF|BEES|IETF|NIFTY|SENSEX|GILT|BOND|SDL|LIQUID|GOLD|SILVER|INVIT|REIT)",
    re.I,
)


def _public_nse_cm_csv() -> pd.DataFrame:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date()
    for offset in range(0, 6):
        day = (today - timedelta(days=offset)).isoformat()
        cache = _CACHE_DIR / f"nse_cm_{day}.csv"
        if cache.exists() and cache.stat().st_size > 1000:
            return pd.read_csv(cache, low_memory=False)
        url = (
            f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/"
            f"{day}/transformed/nse_cm.csv"
        )
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 200 and len(r.content) > 1000:
                cache.write_bytes(r.content)
                return pd.read_csv(io.BytesIO(r.content), low_memory=False)
        except Exception as e:
            logger.warning("NSE scrip CSV %s failed: %s", day, e)
    return pd.DataFrame()


def nse_eq_token_map() -> Dict[str, str]:
    """symbol → instrument token for NSE EQ cash."""
    df = _public_nse_cm_csv()
    if df.empty:
        return {}
    df.columns = [c.strip() for c in df.columns]
    name_col = next((c for c in df.columns if c.lower() == "psymbolname"), None)
    tok_col = next((c for c in df.columns if c.lower() == "psymbol"), None)
    group_col = next((c for c in df.columns if c.lower() == "pgroup"), None)
    if not name_col or not tok_col:
        return {}
    eq = df
    if group_col:
        eq = eq[eq[group_col].astype(str).str.upper() == "EQ"]
    out: Dict[str, str] = {}
    for _, row in eq.iterrows():
        sym = str(row[name_col]).strip().upper()
        if not sym or _SKIP_RE.search(sym):
            continue
        try:
            out[sym] = str(int(float(row[tok_col])))
        except Exception:
            continue
    return out


def listed_eq_count() -> int:
    return len(nse_eq_token_map())


def all_eq_symbols() -> List[str]:
    """Full NSE EQ cash symbol list (sorted), excluding ETF/bond noise."""
    return sorted(nse_eq_token_map().keys())


def search_eq_symbols(q: str, *, limit: int = 40) -> List[str]:
    q = (q or "").upper().strip()
    if not q:
        return []
    listed = all_eq_symbols()
    core = set(CORE_UNIVERSE)

    def rank(s: str) -> tuple:
        # Prefer exact → prefix → shorter liquid names → core index names
        exact = 0 if s == q else 1
        prefix = 0 if s.startswith(q) else 1
        core_boost = 0 if s in core else 1
        return (exact, prefix, core_boost, len(s), s)

    hits = [s for s in listed if q in s]
    hits.sort(key=rank)
    return hits[:limit]


def build_ingest_universe(
    *,
    max_symbols: int = 250,
    prefer: Optional[List[str]] = None,
) -> List[str]:
    """
    Priority merge: preferred (DB) → CORE_UNIVERSE → remaining NSE EQ.

    Caps at max_symbols for Kotak rate limits.
    Pass max_symbols <= 0 to ingest the full NSE EQ cash list (no cap).
    """
    tokens = nse_eq_token_map()
    listed = set(tokens.keys())
    ordered: List[str] = []
    seen: Set[str] = set()
    unlimited = int(max_symbols or 0) <= 0
    cap = len(listed) + len(CORE_UNIVERSE) + 50 if unlimited else int(max_symbols)

    def add(sym: str) -> bool:
        s = sym.strip().upper()
        if not s or s in seen:
            return len(ordered) >= cap
        if listed and s not in listed and s not in CORE_UNIVERSE:
            return len(ordered) >= cap
        seen.add(s)
        ordered.append(s)
        return len(ordered) >= cap

    for s in prefer or []:
        if add(s):
            return ordered[:cap]
    for s in CORE_UNIVERSE:
        if add(s):
            return ordered[:cap]

    # Prefer higher issue capital when available
    df = _public_nse_cm_csv()
    ranked: List[str] = []
    if not df.empty:
        df.columns = [c.strip() for c in df.columns]
        name_col = next((c for c in df.columns if c.lower() == "psymbolname"), None)
        group_col = next((c for c in df.columns if c.lower() == "pgroup"), None)
        cap_col = next((c for c in df.columns if c.lower() == "dissuecapital"), None)
        if name_col:
            eq = df
            if group_col:
                eq = eq[eq[group_col].astype(str).str.upper() == "EQ"]
            if cap_col:
                eq = eq.copy()
                eq["_cap"] = pd.to_numeric(eq[cap_col], errors="coerce").fillna(0)
                eq = eq.sort_values("_cap", ascending=False)
            for sym in eq[name_col].astype(str).str.upper():
                if _SKIP_RE.search(sym):
                    continue
                ranked.append(sym)

    for s in ranked or sorted(listed):
        if add(s):
            break

    return ordered[:cap] if not unlimited else ordered


def coverage_stats(db_symbols: List[str]) -> dict:
    listed = listed_eq_count()
    in_db = len([s for s in db_symbols if s and s != "NIFTY"])
    return {
        "exchange": "NSE",
        "segment": "EQ cash",
        "listed_eq_approx": listed,
        "in_database": in_db,
        "note": (
            "Screens liquid NSE equities for weekly swings — not the full BSE/NSE board "
            "(SME, ETFs, illiquids excluded by design)."
        ),
    }
