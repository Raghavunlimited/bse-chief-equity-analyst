#!/usr/bin/env python3
"""
Generate realistic demo EOD for the liquid universe + NIFTY.
Use when live NSE/Yahoo ingest is unavailable (rate limits / archive down).
Replace with `python run_daily_ingest.py` when network sources work.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.features import recompute_and_store
from app.store import Database
from app.yahoo_eod import CORE_UNIVERSE

# Approximate last prices (INR) for anchoring — not live quotes
ANCHORS = {
    "NIFTY": 22800,
    "RELIANCE": 1210, "TCS": 3850, "HDFCBANK": 1720, "ICICIBANK": 1280,
    "INFY": 1850, "ITC": 420, "SBIN": 820, "BHARTIARTL": 1650,
    "HINDUNILVR": 2500, "LT": 3600, "KOTAKBANK": 1780, "AXISBANK": 1150,
    "BAJFINANCE": 7200, "ASIANPAINT": 2450, "MARUTI": 11200, "SUNPHARMA": 1750,
    "TITAN": 3400, "ULTRACEMCO": 11200, "NESTLEIND": 2300, "WIPRO": 520,
    "POWERGRID": 320, "NTPC": 380, "M&M": 2800, "HCLTECH": 1700,
    "TATAMOTORS": 720, "ADANIENT": 2900, "ADANIPORTS": 1250, "JSWSTEEL": 950,
    "TATASTEEL": 150, "TECHM": 1550, "INDUSINDBK": 1050, "BAJAJFINSV": 1750,
    "ONGC": 270, "COALINDIA": 420, "CIPLA": 1500, "DRREDDY": 1250,
    "GRASIM": 2600, "HINDALCO": 680, "BPCL": 320, "DIVISLAB": 4800,
    "EICHERMOT": 4800, "HEROMOTOCO": 4800, "BRITANNIA": 5600, "APOLLOHOSP": 6800,
    "TATACONSUM": 1100, "BAJAJ-AUTO": 9200, "SBILIFE": 1600, "HDFCLIFE": 680,
    "PIDILITIND": 3000, "SIEMENS": 6800, "DLF": 820, "GODREJCP": 1200,
    "HAVELLS": 1700, "AMBUJACEM": 580, "INDIGO": 4500, "VEDL": 460,
    "IOC": 150, "BANKBARODA": 240, "PNB": 110, "BEL": 280, "HAL": 4500,
}


def _trading_days(n: int = 260) -> list[str]:
    days = []
    d = datetime.now().date()
    # end on last weekday
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return list(reversed(days))


def _series(symbol: str, dates: list[str], market: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    anchor = ANCHORS.get(symbol, float(rng.integers(200, 2000)))
    beta = 0.85 if symbol != "NIFTY" else 1.0
    idio = 0.012 if symbol != "NIFTY" else 0.0
    rets = beta * market + rng.normal(0, idio, size=len(dates))
    # mild drift
    rets = rets + (0.0003 if symbol != "NIFTY" else 0.0002)
    prices = anchor * np.exp(np.cumsum(rets))
    # scale so last close ≈ anchor
    prices = prices * (anchor / prices[-1])

    rows = []
    for i, dt in enumerate(dates):
        close = float(prices[i])
        open_ = close * (1 + float(rng.normal(0, 0.004)))
        high = max(open_, close) * (1 + abs(float(rng.normal(0, 0.006))))
        low = min(open_, close) * (1 - abs(float(rng.normal(0, 0.006))))
        vol = float(rng.integers(800_000, 3_000_000))
        # Volume climaxes on week-ending bars (and last bar) for screenable history
        if symbol != "NIFTY":
            dt_obj = datetime.strptime(dt, "%Y-%m-%d")
            if i == len(dates) - 1 or dt_obj.weekday() == 4:
                vol *= float(rng.uniform(2.3, 3.4))
                high = max(high, close * 1.008)
        prev = float(prices[i - 1]) if i else close
        rows.append(
            {
                "symbol": symbol,
                "trade_date": dt,
                "open": round(open_, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": vol,
                "turnover": round(close * vol, 2),
                "prev_close": round(prev, 2),
            }
        )
    return pd.DataFrame(rows)



def main():
    rng = np.random.default_rng(42)
    dates = _trading_days(260)
    # Mild uptrend so regime allows trades, but not so hot that RS filters die
    market = rng.normal(0.00015, 0.008, size=len(dates))
    market[-60:-20] = rng.normal(0.0008, 0.006, size=40)
    market[-20:] = rng.normal(0.0003, 0.005, size=20)

    db = Database(config.db_path)
    frames = [_series("NIFTY", dates, market, rng)]
    for i, sym in enumerate(CORE_UNIVERSE[:55]):
        m = market.copy()
        # Controlled setups: grind up, mild pause, then volume thrust (RSI ~55-65)
        if i % 5 == 0:
            m[-25:-8] = rng.normal(0.0010, 0.005, size=17)
            m[-8:-2] = rng.normal(0.0001, 0.004, size=6)
            m[-2:] = rng.normal(0.008, 0.003, size=2)
        frames.append(_series(sym, dates, m, rng))

    all_df = pd.concat(frames, ignore_index=True)
    rows = db.upsert_eod_data(all_df)

    # Rewrite last 30 sessions for textbook swing setups (RSI mid-band, RS > NIFTY)
    setup_syms = ["RELIANCE", "HDFCBANK", "INFY"]
    patched = []
    for si, sym in enumerate(setup_syms):
        hist = all_df[all_df["symbol"] == sym].sort_values("trade_date").reset_index(drop=True)
        if len(hist) < 40:
            continue
        local = np.random.default_rng(100 + si)
        px = float(hist.iloc[-31]["close"])
        for i in range(len(hist) - 30, len(hist)):
            step = i - (len(hist) - 30)
            noise = float(local.normal(0, 0.004))
            if step < 20:
                day = 0.0045 if step % 3 else -0.002
                px *= 1 + day + noise * 0.25
                vol = float(local.integers(1_200_000, 2_200_000))
            elif step < 28:
                # Longer digestion to pull RSI into mid-60s
                px *= 1 + float(local.uniform(-0.005, 0.001))
                vol = float(local.integers(900_000, 1_500_000))
            else:
                px *= 1.012
                vol = float(local.integers(5_000_000, 8_000_000))
            hist.at[i, "close"] = round(px, 2)
            hist.at[i, "open"] = round(px * (1 + float(local.normal(-0.001, 0.003))), 2)
            hist.at[i, "high"] = round(max(float(hist.at[i, "open"]), px) * 1.006, 2)
            hist.at[i, "low"] = round(min(float(hist.at[i, "open"]), px) * 0.994, 2)
            hist.at[i, "volume"] = vol
            hist.at[i, "turnover"] = round(px * vol, 2)
            hist.at[i, "prev_close"] = float(hist.iloc[i - 1]["close"])
        patched.append(hist.iloc[-30:])
    if patched:
        db.upsert_eod_data(pd.concat(patched, ignore_index=True))

    ind = recompute_and_store(db, lookback_days=400)
    from app.meta import set_meta

    set_meta(config.db_path, "data_source", "demo")
    set_meta(
        config.db_path,
        "data_note",
        "Synthetic demo prices for UI/wiring only — NOT real market data. Run Refresh for live Yahoo/NSE.",
    )
    fresh = db.freshness(config.max_data_age_days)
    print(
        {
            "status": "ok",
            "source": "demo_seed",
            "eod_rows": rows,
            "indicator_rows": ind,
            "freshness": fresh,
            "message": "Demo EOD seeded. Run live ingest when Yahoo/NSE are available.",
        }
    )




if __name__ == "__main__":
    main()
