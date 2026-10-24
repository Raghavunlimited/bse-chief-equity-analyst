"""
Kotak Neo historical candles → EOD rows.

Only needs KOTAK_CONSUMER_KEY (Trade API token from Neo app).
Historical/search do NOT require TOTP session per Kotak SDK docs.

Docs: https://github.com/Kotak-Neo/kotak-neo-python
"""
from __future__ import annotations

import io
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "kotak_cache"

# One Session per worker thread (requests.Session is not thread-safe).
_thread_local = threading.local()
_token_lock = threading.Lock()


def _thread_session() -> requests.Session:
    sess = getattr(_thread_local, "session", None)
    if sess is None:
        sess = requests.Session()
        _thread_local.session = sess
    return sess


# Prod hosts used by the official SDK
_BASES = (
    "https://mis.kotaksecurities.com",
    "https://cis.kotaksecurities.com",
)

HIST_PATH = "/market-data/1.0/historical/details"
SCRIP_PATH = "/script-details/1.0/masterscrip/file-paths"

# Well-known NSE cash tokens (fallback if scrip master fails)
_KNOWN_TOKENS: Dict[str, str] = {
    "RELIANCE": "2885",
    "TCS": "11536",
    "INFY": "1594",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "ITC": "1660",
    "BHARTIARTL": "10604",
    "LT": "11483",
    "AXISBANK": "5900",
    "KOTAKBANK": "1922",
    "ASIANPAINT": "236",
    "MARUTI": "10999",
    "SUNPHARMA": "3351",
    "TITAN": "3506",
    "BAJFINANCE": "317",
    "WIPRO": "3787",
    "HCLTECH": "7229",
    "ONGC": "2475",
    "NTPC": "11630",
    "POWERGRID": "14977",
    "TATAMOTORS": "3456",
    "TATASTEEL": "3499",
    "JSWSTEEL": "11723",
    "HINDUNILVR": "1394",
    "ULTRACEMCO": "11532",
    "NESTLEIND": "17963",
    "TECHM": "13538",
    "ADANIENT": "25",
    "ADANIPORTS": "15083",
    "COALINDIA": "2031",
    "BPCL": "526",
    "INDUSINDBK": "5258",
    "BAJAJFINSV": "16675",
    "M&M": "2031",
    "DRREDDY": "881",
    "CIPLA": "694",
    "EICHERMOT": "910",
    "GRASIM": "1232",
    "HINDALCO": "1363",
    "APOLLOHOSP": "157",
    "DIVISLAB": "10940",
    "BRITANNIA": "547",
    "HEROMOTOCO": "1348",
    "SBILIFE": "21808",
    "HDFCLIFE": "467",
}


def reload_env() -> None:
    load_dotenv(_ENV_PATH, override=True)


def consumer_key() -> Optional[str]:
    reload_env()
    return (
        os.getenv("KOTAK_CONSUMER_KEY")
        or os.getenv("NEO_CONSUMER_KEY")
        or os.getenv("KOTAK_NEO_CONSUMER_KEY")
        or ""
    ).strip() or None


def is_configured() -> bool:
    return bool(consumer_key())


def status() -> dict:
    reload_env()
    key = consumer_key()
    out = {
        "configured": bool(key),
        "consumer_key_present": bool(key),
        "note": "Historical needs only consumer key (Neo → More → Trade API).",
    }
    # Path only in debug — avoids leaking host filesystem layout (CTO readiness)
    if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
        out["env_path"] = str(_ENV_PATH)
    return out


def _headers(key: str) -> dict:
    return {
        "Authorization": key,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }


def _base_url() -> str:
    override = (os.getenv("KOTAK_BASE_URL") or "").strip().rstrip("/")
    return override or _BASES[0]


def _get_json(path: str, params: Optional[dict] = None) -> tuple[int, Any]:
    """
    Single-host request via thread-local Session. On HTTP 429 this worker
    alone applies exponential backoff (does not fan-out hosts on 4xx).
    """
    key = consumer_key()
    if not key:
        return 0, {"error": "missing consumer key"}
    base = _base_url()
    url = f"{base}{path}"
    last_status, last_body = 0, None
    sess = _thread_session()
    max_attempts = 6
    host_switched = False
    for attempt in range(max_attempts):
        try:
            r = sess.get(url, params=params, headers=_headers(key), timeout=30)
            last_status = r.status_code
            try:
                last_body = r.json()
            except Exception:
                last_body = {"raw": r.text[:300]}
            if r.status_code == 200:
                return r.status_code, last_body
            if r.status_code == 429:
                # Per-worker exponential backoff: 1.5s → 3 → 6 → 12 → 24 → 48 (cap 60)
                delay = min(60.0, 1.5 * (2**attempt))
                logger.warning(
                    "Kotak %s → HTTP 429; worker backoff %.1fs (attempt %s/%s)",
                    path,
                    delay,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(delay)
                continue
            # 4xx other than 429: don't retry other hosts
            logger.warning("Kotak %s → HTTP %s", path, r.status_code)
            return last_status, last_body
        except Exception as e:
            logger.warning("Kotak request failed %s: %s", url, e)
            last_body = {"error": str(e)}
            # try alternate host once on network failure
            alt = next((b for b in _BASES if b != base), None)
            if alt and not host_switched:
                url = f"{alt}{path}"
                host_switched = True
                continue
            break
    return last_status, last_body


def _date_window(days: int) -> tuple[str, str]:
    """Kotak daily interval allows ≤180 calendar days inclusive → use 179 span."""
    days = min(max(int(days), 5), 179)
    end = datetime.now().date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _load_nse_cm_scrip() -> pd.DataFrame:
    """
    NSE cash scrip master for token lookup.

    Prefer Kotak's public lapi CSV (no auth). The authenticated
    /masterscrip/file-paths endpoint often returns HTTP 424
    "Consumer key is invalid" even when historical candles work.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date()
    for offset in range(0, 5):
        day = (today - timedelta(days=offset)).isoformat()
        cache_file = _CACHE_DIR / f"nse_cm_{day}.csv"
        if cache_file.exists() and cache_file.stat().st_size > 1000:
            return pd.read_csv(cache_file, low_memory=False)
        url = f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{day}/transformed/nse_cm.csv"
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 1000:
                cache_file.write_bytes(r.content)
                return pd.read_csv(io.BytesIO(r.content), low_memory=False)
        except Exception as e:
            logger.warning("Kotak public scrip CSV %s failed: %s", day, e)

    # Last resort: authenticated file-paths (may 424)
    code, body = _get_json(SCRIP_PATH)
    if code != 200 or not isinstance(body, dict):
        logger.warning("Kotak scrip master HTTP %s (using known tokens only)", code)
        return pd.DataFrame()
    paths = (body.get("data") or {}).get("filesPaths") or body.get("filesPaths") or []
    csv_url = next((p for p in paths if "nse_cm" in str(p).lower()), paths[0] if paths else None)
    if not csv_url:
        return pd.DataFrame()
    try:
        r = requests.get(csv_url, timeout=60)
        r.raise_for_status()
        cache_file = _CACHE_DIR / f"nse_cm_{today.isoformat()}.csv"
        cache_file.write_bytes(r.content)
        return pd.read_csv(io.BytesIO(r.content), low_memory=False)
    except Exception as e:
        logger.warning("Kotak scrip CSV download failed: %s", e)
        return pd.DataFrame()


_token_cache: Dict[str, str] = {}


def _warm_token_cache() -> None:
    with _token_lock:
        if len(_token_cache) > 100:
            return
        try:
            from app.universe_nse import nse_eq_token_map

            _token_cache.update(nse_eq_token_map())
        except Exception as e:
            logger.warning("token map warm failed: %s", e)
        _token_cache.update(_KNOWN_TOKENS)


def resolve_token(symbol: str) -> Optional[str]:
    """Map trading symbol → NSE instrument token string."""
    sym = symbol.upper().strip()
    with _token_lock:
        if sym in _token_cache:
            return _token_cache[sym]
        if sym in _KNOWN_TOKENS:
            _token_cache[sym] = _KNOWN_TOKENS[sym]
            return _KNOWN_TOKENS[sym]

    df = _load_nse_cm_scrip()
    if df.empty:
        return None
    df.columns = [c.strip() for c in df.columns]
    name_col = next((c for c in df.columns if c.lower() in ("psymbolname", "p_symbol_name")), None)
    trd_col = next((c for c in df.columns if c.lower() in ("ptrdsymbol", "p_trd_symbol")), None)
    tok_col = next((c for c in df.columns if c.lower() in ("psymbol", "p_symbol")), None)
    group_col = next((c for c in df.columns if c.lower() in ("pgroup", "p_group")), None)
    if not tok_col:
        return None

    candidates = df
    if name_col:
        candidates = candidates[candidates[name_col].astype(str).str.upper() == sym]
    if candidates.empty and trd_col:
        candidates = df[df[trd_col].astype(str).str.upper().isin([sym, f"{sym}-EQ"])]
    if candidates.empty:
        return None
    if group_col is not None and (candidates[group_col].astype(str) == "EQ").any():
        candidates = candidates[candidates[group_col].astype(str) == "EQ"]
    token = str(int(float(candidates.iloc[0][tok_col])))
    with _token_lock:
        _token_cache[sym] = token
    return token


def _candles_to_df(symbol: str, candles: list) -> pd.DataFrame:
    rows = []
    for c in candles:
        if not isinstance(c, (list, tuple)) or len(c) < 6:
            continue
        ts = str(c[0])
        trade_date = ts[:10]
        o, h, l, cl, vol = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5] or 0)
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": o,
                "high": h,
                "low": l,
                "close": cl,
                "volume": vol,
                "turnover": cl * vol,
                "prev_close": None,
            }
        )
    df = pd.DataFrame(rows).sort_values("trade_date")
    if df.empty:
        return df
    df["prev_close"] = df["close"].shift(1).fillna(df["close"])
    return df


def fetch_symbol_daily(symbol: str, *, days: int = 179) -> pd.DataFrame:
    token = resolve_token(symbol)
    if not token:
        logger.warning("Kotak: no token for %s", symbol)
        return pd.DataFrame()

    start, end = _date_window(days)
    neosymbol = f"nse_cm|{token}"
    code, body = _get_json(
        HIST_PATH,
        {
            "neosymbol": neosymbol,
            "interval": "D",
            "fromdate": start,
            "todate": end,
        },
    )
    if code != 200 or not isinstance(body, dict):
        logger.warning("Kotak hist %s HTTP %s: %s", symbol, code, str(body)[:160])
        return pd.DataFrame()
    if str(body.get("status", "")).lower() not in ("success", "ok", ""):
        if body.get("fault") or body.get("error"):
            logger.warning("Kotak hist %s error: %s", symbol, str(body)[:200])
            return pd.DataFrame()
    candles = (body.get("data") or {}).get("candles") or body.get("candles") or []
    return _candles_to_df(symbol, candles)


def fetch_nifty_daily(days: int = 179) -> pd.DataFrame:
    """NIFTY 50 — Kotak accepts neosymbol `nse_cm|Nifty 50` (token 26000 is invalid)."""
    start, end = _date_window(days)
    code, body = _get_json(
        HIST_PATH,
        {
            "neosymbol": "nse_cm|Nifty 50",
            "interval": "D",
            "fromdate": start,
            "todate": end,
        },
    )
    if code != 200 or not isinstance(body, dict):
        logger.warning("Kotak NIFTY HTTP %s: %s", code, str(body)[:160])
        return pd.DataFrame()
    candles = (body.get("data") or {}).get("candles") or []
    if not candles:
        return pd.DataFrame()
    df = _candles_to_df("NIFTY", candles)
    df["turnover"] = 0.0
    return df


def fetch_symbols(
    symbols: Iterable[str],
    *,
    days: int = 179,
    pause: float = 0.12,
    max_symbols: Optional[int] = None,
    on_progress: Optional[Callable[[int, str, bool], None]] = None,
    workers: Optional[int] = None,
) -> pd.DataFrame:
    """
    Concurrent Kotak historical fetch.

    Bounded ThreadPoolExecutor (≤8). Each worker uses a thread-local Session,
    soft-paces with ``pause`` (INGEST_PAUSE_SEC), and backs off on 429 alone.
    Frames are collected then concatenated once for a single batch upsert.
    """
    if not is_configured():
        return pd.DataFrame()
    # Warm caches once on the main thread before workers start
    _warm_token_cache()
    _load_nse_cm_scrip()

    sym_list = [str(s).upper().strip() for s in symbols if s]
    if max_symbols is not None:
        sym_list = sym_list[:max_symbols]
    if not sym_list:
        return pd.DataFrame()

    try:
        from app.config import config as _cfg

        default_workers = int(getattr(_cfg, "ingest_workers", 4))
    except Exception:
        default_workers = 4
    n_workers = max(1, min(8, int(workers if workers is not None else default_workers)))

    frames: List[pd.DataFrame] = []
    progress_lock = threading.Lock()
    done = 0

    def _one(sym: str) -> tuple[str, pd.DataFrame]:
        df = fetch_symbol_daily(sym, days=days)
        # Soft pacing per worker (INGEST_PAUSE_SEC) — avoid stampeding the API
        if pause > 0:
            time.sleep(pause)
        return sym, df

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = {pool.submit(_one, sym): sym for sym in sym_list}
        for fut in as_completed(futs):
            sym = futs[fut]
            ok = False
            df: Optional[pd.DataFrame] = None
            try:
                sym, df = fut.result()
                ok = df is not None and not df.empty
            except Exception as e:
                logger.warning("Kotak concurrent fetch %s: %s", sym, e)
            with progress_lock:
                if ok and df is not None:
                    frames.append(df)
                done += 1
                cur = done
                if on_progress:
                    try:
                        on_progress(cur, sym, ok)
                    except Exception:
                        pass

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def probe() -> dict:
    """Probe historical candles (scrip-master 424 is common and ignored)."""
    st = status()
    if not st["configured"]:
        return {
            "ok": False,
            "step": "config",
            "message": (
                "Kotak consumer key missing. In Neo app: More → Trade API → "
                "Create Application → copy token into KOTAK_CONSUMER_KEY in backend/.env"
            ),
            "status": st,
        }

    # Historical is the real requirement — works even when scrip master returns 424
    df = fetch_symbol_daily("RELIANCE", days=30)
    if df.empty:
        # Try another liquid name in case RELIANCE token map is stale
        df = fetch_symbol_daily("HDFCBANK", days=30)
    if df.empty:
        code, body = _get_json(SCRIP_PATH)
        detail = ""
        if isinstance(body, dict):
            detail = str(body.get("message") or body)[:160]
        return {
            "ok": False,
            "step": "historical",
            "http_status": code or None,
            "message": (
                "Kotak historical candles failed. Confirm the token from Neo → More → "
                "Trade API → API Dashboard (Access Token), not an old OAuth secret."
            ),
            "detail": detail,
            "status": st,
        }
    return {
        "ok": True,
        "step": "historical",
        "message": f"Kotak OK — {len(df)} daily candles (scrip-master 424 is harmless if seen).",
        "candle_count": int(len(df)),
        "status": st,
    }
