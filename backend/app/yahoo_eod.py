"""EOD via Yahoo chart API. Prefers curl (more reliable than urllib here)."""
from __future__ import annotations

import json
import logging
import random
import subprocess
import time
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import quote

import pandas as pd

logger = logging.getLogger(__name__)

CHART_HOSTS = [
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
]
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _curl_json(url: str, params: dict) -> Optional[dict]:
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    full = f"{url}?{qs}"
    try:
        proc = subprocess.run(
            [
                "curl",
                "-sL",
                "-A",
                UA,
                "-H",
                "Accept: application/json",
                "--max-time",
                "30",
                full,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        body = (proc.stdout or "").strip()
        if proc.returncode != 0 or not body:
            return None
        if body.startswith("<") or body.startswith("Too Many"):
            return None
        return json.loads(body)
    except Exception as e:
        logger.warning("curl fetch failed: %s", e)
        return None


def fetch_chart(
    yahoo_symbol: str,
    range_: str = "1y",
    session=None,  # unused; kept for call compatibility
    retries: int = 3,
) -> pd.DataFrame:
    last_err = None
    encoded = quote(yahoo_symbol, safe="")
    for attempt in range(retries):
        url = CHART_HOSTS[attempt % len(CHART_HOSTS)].format(symbol=encoded)
        payload = _curl_json(url, {"range": range_, "interval": "1d"})
        if not payload:
            last_err = "empty"
            time.sleep(1.2 + attempt)
            continue

        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return pd.DataFrame()
        block = result[0]
        ts = block.get("timestamp") or []
        qblock = (block.get("indicators") or {}).get("quote") or [{}]
        q = qblock[0]
        if not ts:
            return pd.DataFrame()
        df = pd.DataFrame(
            {
                "trade_date": [
                    datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") for t in ts
                ],
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "close": q.get("close"),
                "volume": q.get("volume"),
            }
        )
        df = df.dropna(subset=["close"])
        df["prev_close"] = df["close"].shift(1).fillna(df["close"])
        df["turnover"] = df["close"] * df["volume"].fillna(0)
        return df
    logger.warning("Yahoo chart failed for %s: %s", yahoo_symbol, last_err)
    return pd.DataFrame()


def to_eod_rows(symbol: str, hist: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        return hist
    out = hist.copy()
    out["symbol"] = symbol
    return out[
        [
            "symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "prev_close",
        ]
    ]


def fetch_nifty(range_: str = "2y", session=None) -> pd.DataFrame:
    hist = fetch_chart("^NSEI", range_=range_)
    return to_eod_rows("NIFTY", hist)


def fetch_symbols(
    symbols: Iterable[str],
    range_: str = "1y",
    pause: float = 0.8,
    max_symbols: Optional[int] = None,
    on_progress=None,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    count = 0
    sym_list = list(symbols)
    for idx, sym in enumerate(sym_list, start=1):
        if max_symbols is not None and count >= max_symbols:
            break
        hist = fetch_chart(f"{sym}.NS", range_=range_)
        ok = not hist.empty
        if ok:
            frames.append(to_eod_rows(sym, hist))
            count += 1
            if count % 10 == 0:
                logger.info("Yahoo EOD: %s symbols loaded", count)
        if on_progress:
            try:
                on_progress(idx, sym, ok)
            except Exception:
                pass
        time.sleep(pause + random.uniform(0, 0.3))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


CORE_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "SBIN", "BHARTIARTL",
    "HINDUNILVR", "LT", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI",
    "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND", "WIPRO", "POWERGRID", "NTPC",
    "M&M", "HCLTECH", "TATAMOTORS", "ADANIENT", "ADANIPORTS", "JSWSTEEL", "TATASTEEL",
    "TECHM", "INDUSINDBK", "BAJAJFINSV", "ONGC", "COALINDIA", "CIPLA", "DRREDDY",
    "GRASIM", "HINDALCO", "BPCL", "DIVISLAB", "EICHERMOT", "HEROMOTOCO", "BRITANNIA",
    "APOLLOHOSP", "TATACONSUM", "BAJAJ-AUTO", "SBILIFE", "HDFCLIFE", "PIDILITIND",
    "SIEMENS", "DLF", "GODREJCP", "HAVELLS", "AMBUJACEM", "INDIGO", "VEDL", "IOC",
    "BANKBARODA", "PNB", "CANBK", "FEDERALBNK", "IDFCFIRSTB", "CHOLAFIN", "MUTHOOTFIN",
    "PERSISTENT", "COFORGE", "LTIM", "MPHASIS", "POLYCAB", "DIXON",
    "LUPIN", "AUROPHARMA", "TORNTPHARM", "ZYDUSLIFE", "ALKEM",
    "TRENT", "DMART", "VOLTAS", "BERGEPAINT", "COLPAL",
    "DABUR", "MARICO", "IRCTC", "NAUKRI", "ZOMATO",
    "PIIND", "SRF", "PETRONET", "GAIL", "IGL", "CONCOR",
    "TVSMOTOR", "MRF", "MOTHERSON", "BEL", "HAL", "BHEL",
    "ABB", "CGPOWER", "ASTRAL", "PFC", "RECLTD", "IRFC",
    "MCX", "CDSL", "IEX", "BSE",
]


def days_to_range(days: int) -> str:
    if days <= 30:
        return "1mo"
    if days <= 100:
        return "3mo"
    if days <= 200:
        return "6mo"
    if days <= 400:
        return "1y"
    return "2y"
