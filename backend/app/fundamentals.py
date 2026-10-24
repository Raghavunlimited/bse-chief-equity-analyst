"""
Stock fundamentals with multi-source fetch + SQLite cache.

Priority: cache → Screener.in HTML → Yahoo quote (v7) → Yahoo quoteSummary → honest unavailable.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_COOKIE_JAR = Path(tempfile.gettempdir()) / "swing_desk_yahoo_cookies.txt"
_crumb_cache: dict[str, str] = {"crumb": "", "ts": "0"}
_CACHE_DB = Path(__file__).resolve().parent.parent / "data" / "fundamentals_cache.db"
_CACHE_TTL_SEC = 7 * 24 * 3600
_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)


def _curl(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _cache_conn() -> sqlite3.Connection:
    _CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamentals (
            symbol TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    return conn


def _cache_get(symbol: str) -> Optional[dict]:
    try:
        with _cache_conn() as conn:
            row = conn.execute(
                "SELECT payload, updated_at FROM fundamentals WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        if not row:
            return None
        payload, ts = row
        if time.time() - float(ts) > _CACHE_TTL_SEC:
            return None
        data = json.loads(payload)
        data["cached"] = True
        return data
    except Exception as e:
        logger.warning("fund cache get: %s", e)
        return None


def _cache_set(symbol: str, data: dict) -> None:
    if not data.get("available"):
        return
    try:
        with _cache_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals(symbol, payload, updated_at) VALUES (?,?,?)",
                (symbol, json.dumps(data), time.time()),
            )
            conn.commit()
    except Exception as e:
        logger.warning("fund cache set: %s", e)


def _parse_indian_number(raw: str) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in ("—", "-", "NA", "N/A"):
        return None
    s = s.replace(",", "").replace("₹", "").replace("%", "").strip()
    # Screener market caps like "16,05,186 Cr." already stripped commas → 1605186
    s = re.sub(r"\s*Cr\.?$", "", s, flags=re.I).strip()
    try:
        return float(s)
    except ValueError:
        return None


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _from_screener(symbol: str) -> dict[str, Any]:
    """Parse Screener.in company page top ratios (public HTML)."""
    out: dict[str, Any] = {"symbol": symbol, "source": "screener", "available": False}
    urls = [
        f"https://www.screener.in/company/{quote(symbol)}/consolidated/",
        f"https://www.screener.in/company/{quote(symbol)}/",
    ]
    html = ""
    for url in urls:
        try:
            r = _SESSION.get(url, timeout=25)
            if r.status_code == 200 and "Stock P/E" in r.text:
                html = r.text
                break
            if r.status_code == 200 and len(r.text) > 2000:
                html = r.text  # try parse anyway
                break
        except Exception as e:
            logger.warning("screener fetch %s: %s", url, e)
    if not html:
        out["message"] = "Screener page unavailable"
        return out

    name_m = re.search(
        r'<h1[^>]*>\s*(?:<[^>]+>\s*)*([^<\n]+)',
        html,
        re.I,
    )
    company = _strip_html(name_m.group(1)) if name_m else None
    if company:
        company = re.sub(r"\s+", " ", company).strip()

    pairs = re.findall(
        r'<li[^>]*>\s*<span class="name">\s*([^<]+?)\s*</span>\s*'
        r'<span[^>]*class="[^"]*value[^"]*"[^>]*>(.*?)</span>\s*</li>',
        html,
        re.S,
    )
    ratios: dict[str, str] = {}
    for name, val_html in pairs:
        key = name.strip()
        ratios[key] = _strip_html(val_html)

    if not ratios:
        out["message"] = "Could not parse Screener ratios"
        return out

    mcap_cr = _parse_indian_number(ratios.get("Market Cap", ""))
    pe = _parse_indian_number(ratios.get("Stock P/E", ""))
    book = _parse_indian_number(ratios.get("Book Value", ""))
    div_y = _parse_indian_number(ratios.get("Dividend Yield", ""))
    roce = _parse_indian_number(ratios.get("ROCE", ""))
    roe = _parse_indian_number(ratios.get("ROE", ""))
    face = _parse_indian_number(ratios.get("Face Value", ""))
    price = _parse_indian_number(ratios.get("Current Price", ""))

    hi_lo = ratios.get("High / Low", "")
    hi = lo = None
    hl = re.findall(r"[\d,.]+", hi_lo.replace("₹", ""))
    if len(hl) >= 2:
        hi = _parse_indian_number(hl[0])
        lo = _parse_indian_number(hl[1])

    pb = None
    if price and book and book > 0:
        pb = round(price / book, 2)

    out.update(
        {
            "available": True,
            "name": company or symbol,
            "currency": "INR",
            "live_price": price,
            "market_cap_cr": mcap_cr,
            "market_cap": (mcap_cr * 1e7) if mcap_cr is not None else None,
            "pe_ttm": pe,
            "book_value": book,
            "pb": pb,
            "dividend_yield_pct": div_y,
            "roce_pct": roce,
            "roe_pct": roe,
            "face_value": face,
            "fifty_two_week_high": hi,
            "fifty_two_week_low": lo,
            "ratios_raw": ratios,
        }
    )
    return out


def _ensure_crumb() -> Optional[str]:
    now = time.time()
    if _crumb_cache["crumb"] and now - float(_crumb_cache["ts"] or 0) < 3000:
        return _crumb_cache["crumb"]

    jar = str(_COOKIE_JAR)
    _curl(["curl", "-sL", "-c", jar, "-b", jar, "-A", UA, "https://fc.yahoo.com", "-o", "/dev/null"])
    crumb_proc = _curl(
        ["curl", "-sL", "-c", jar, "-b", jar, "-A", UA, "https://query2.finance.yahoo.com/v1/test/getcrumb"]
    )
    crumb = (crumb_proc.stdout or "").strip()
    if not crumb or "<" in crumb or "Too Many" in crumb:
        logger.warning("Yahoo crumb failed: %s", crumb[:80])
        return None
    _crumb_cache["crumb"] = crumb
    _crumb_cache["ts"] = str(now)
    return crumb


def _curl_json(url: str, *, use_crumb: bool = False) -> Optional[dict]:
    jar = str(_COOKIE_JAR)
    full = url
    if use_crumb:
        crumb = _ensure_crumb()
        if not crumb:
            return None
        sep = "&" if "?" in url else "?"
        full = f"{url}{sep}crumb={quote(crumb, safe='')}"
    proc = _curl(
        [
            "curl",
            "-sL",
            "-c",
            jar,
            "-b",
            jar,
            "-A",
            UA,
            "-H",
            "Accept: application/json",
            "--max-time",
            "25",
            full,
        ]
    )
    body = (proc.stdout or "").strip()
    if not body or body.startswith("<"):
        return None
    if "Unauthorized" in body or "Too Many" in body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _fmt_num(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, dict):
        x = x.get("raw", x.get("fmt"))
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _from_quote_v7(symbol: str) -> dict[str, Any]:
    """Lightweight Yahoo v7 quote — often works without crumb."""
    ysym = quote(f"{symbol}.NS", safe="")
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ysym}"
    payload = _curl_json(url, use_crumb=False)
    out: dict[str, Any] = {"symbol": symbol, "source": "yahoo_quote", "available": False}
    if not payload:
        return out
    try:
        results = ((payload.get("quoteResponse") or {}).get("result")) or []
        if not results:
            return out
        q = results[0]
        mcap = _fmt_num(q.get("marketCap"))
        out.update(
            {
                "available": True,
                "name": q.get("longName") or q.get("shortName") or symbol,
                "currency": q.get("currency") or "INR",
                "live_price": _fmt_num(q.get("regularMarketPrice")),
                "prev_close": _fmt_num(q.get("regularMarketPreviousClose")),
                "day_change_pct": _fmt_num(q.get("regularMarketChangePercent")),
                "market_cap": mcap,
                "market_cap_cr": round(mcap / 1e7, 1) if mcap else None,
                "pe_ttm": _fmt_num(q.get("trailingPE")),
                "pb": _fmt_num(q.get("priceToBook")),
                "eps_ttm": _fmt_num(q.get("epsTrailingTwelveMonths")),
                "dividend_yield": _fmt_num(q.get("trailingAnnualDividendYield")),
                "fifty_two_week_high": _fmt_num(q.get("fiftyTwoWeekHigh")),
                "fifty_two_week_low": _fmt_num(q.get("fiftyTwoWeekLow")),
                "average_volume": _fmt_num(q.get("averageDailyVolume3Month")),
            }
        )
        if out.get("dividend_yield") is not None and out["dividend_yield"] < 1:
            out["dividend_yield_pct"] = round(out["dividend_yield"] * 100, 2)
    except Exception as e:
        logger.warning("quote v7 parse: %s", e)
    return out


def _from_quote_summary(symbol: str) -> dict[str, Any]:
    ysym = quote(f"{symbol}.NS", safe="")
    modules = "summaryDetail,defaultKeyStatistics,financialData,price"
    url = (
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ysym}"
        f"?modules={modules}"
    )
    payload = _curl_json(url, use_crumb=True)
    out: dict[str, Any] = {"symbol": symbol, "source": "yahoo_summary", "available": False}
    if not payload:
        out["message"] = "Fundamentals unavailable (Yahoo auth/rate limit)"
        return out

    try:
        res = (payload.get("quoteSummary") or {}).get("result") or []
        if not res:
            out["message"] = "No fundamentals payload"
            return out
        block = res[0]
        price = block.get("price") or {}
        summary = block.get("summaryDetail") or {}
        keystats = block.get("defaultKeyStatistics") or {}
        fin = block.get("financialData") or {}

        mcap = _fmt_num(price.get("marketCap") or summary.get("marketCap"))
        out.update(
            {
                "available": True,
                "name": price.get("longName") or price.get("shortName") or symbol,
                "currency": price.get("currency") or "INR",
                "live_price": _fmt_num(price.get("regularMarketPrice")),
                "market_cap": mcap,
                "market_cap_cr": round(mcap / 1e7, 1) if mcap else None,
                "pe_ttm": _fmt_num(summary.get("trailingPE")),
                "pe_forward": _fmt_num(summary.get("forwardPE")),
                "pb": _fmt_num(summary.get("priceToBook") or keystats.get("priceToBook")),
                "eps_ttm": _fmt_num(keystats.get("trailingEps")),
                "dividend_yield": _fmt_num(summary.get("dividendYield")),
                "roe": _fmt_num(fin.get("returnOnEquity")),
                "profit_margin": _fmt_num(fin.get("profitMargins")),
                "revenue_growth": _fmt_num(fin.get("revenueGrowth")),
                "earnings_growth": _fmt_num(fin.get("earningsGrowth")),
                "debt_to_equity": _fmt_num(fin.get("debtToEquity")),
                "current_ratio": _fmt_num(fin.get("currentRatio")),
                "target_mean": _fmt_num(fin.get("targetMeanPrice")),
                "recommendation": fin.get("recommendationKey"),
                "fifty_two_week_high": _fmt_num(summary.get("fiftyTwoWeekHigh")),
                "fifty_two_week_low": _fmt_num(summary.get("fiftyTwoWeekLow")),
            }
        )
        if out.get("roe") is not None and abs(out["roe"]) <= 5:
            out["roe_pct"] = round(out["roe"] * 100, 2)
        if out.get("profit_margin") is not None and abs(out["profit_margin"]) <= 5:
            out["profit_margin_pct"] = round(out["profit_margin"] * 100, 2)
        if out.get("dividend_yield") is not None and out["dividend_yield"] < 1:
            out["dividend_yield_pct"] = round(out["dividend_yield"] * 100, 2)
    except Exception as e:
        logger.exception("parse fundamentals: %s", e)
        out["message"] = str(e)
    return out


def _merge_prefer(base: dict, extra: dict) -> dict:
    """Fill missing keys from extra into base."""
    merged = dict(base)
    for k, v in extra.items():
        if k in ("symbol", "source", "available", "message", "cached", "ratios_raw"):
            continue
        if merged.get(k) is None and v is not None:
            merged[k] = v
    return merged


def fetch_live_quote(symbol: str) -> dict[str, Any]:
    q = _from_quote_v7(symbol)
    if q.get("available"):
        return {
            "symbol": symbol,
            "available": True,
            "name": q.get("name"),
            "live_price": q.get("live_price"),
            "prev_close": q.get("prev_close"),
            "day_change_pct": q.get("day_change_pct"),
            "currency": q.get("currency") or "INR",
        }
    sc = _from_screener(symbol)
    if sc.get("available"):
        return {
            "symbol": symbol,
            "available": True,
            "name": sc.get("name"),
            "live_price": sc.get("live_price"),
            "currency": "INR",
        }
    return {"symbol": symbol, "available": False}


def fetch_fundamentals(symbol: str, *, bypass_cache: bool = False) -> dict[str, Any]:
    symbol = symbol.upper().strip()
    if not bypass_cache:
        cached = _cache_get(symbol)
        if cached:
            return cached

    screener = _from_screener(symbol)
    if screener.get("available"):
        # Enrich with Yahoo fields when available (EPS, margins, D/E)
        light = _from_quote_v7(symbol)
        if light.get("available"):
            screener = _merge_prefer(screener, light)
            if light.get("day_change_pct") is not None:
                screener["day_change_pct"] = light["day_change_pct"]
            if light.get("prev_close") is not None:
                screener["prev_close"] = light["prev_close"]
        _cache_set(symbol, screener)
        return screener

    rich = _from_quote_summary(symbol)
    if rich.get("available"):
        _cache_set(symbol, rich)
        return rich

    light = _from_quote_v7(symbol)
    if light.get("available"):
        light["message"] = (
            "Partial fundamentals (quote feed). Full ratios may appear after cache refresh."
        )
        _cache_set(symbol, light)
        return light

    return {
        "symbol": symbol,
        "source": "none",
        "available": False,
        "message": screener.get("message")
        or rich.get("message")
        or "Fundamentals temporarily unavailable — try again in a minute.",
    }


def fetch_fundamentals_many(
    symbols: Iterable[str],
    *,
    max_workers: int = 4,
    bypass_cache: bool = False,
) -> dict[str, dict[str, Any]]:
    """Parallel fundamentals for pick cards / warm cache. Caps workers for Screener."""
    syms = [str(s).upper().strip() for s in symbols if s]
    if not syms:
        return {}
    workers = max(1, min(4, int(max_workers)))
    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(fetch_fundamentals, s, bypass_cache=bypass_cache): s for s in syms
        }
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                out[sym] = fut.result()
            except Exception as e:
                logger.warning("fundamentals_many %s: %s", sym, e)
                out[sym] = {
                    "symbol": sym,
                    "available": False,
                    "source": "none",
                    "message": str(e),
                }
    return out
