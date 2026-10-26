"""Phase 4 — chart workstation payload (EMA/VWAP/RSI/MACD/PDH, intervals)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.chart_data import (  # noqa: E402
    compute_session_vwap_bands,
    ema_ribbon,
    macd_series,
    rsi_series,
)


def _synth_bars(n=80, start=1_700_000_000, px=100.0):
    bars = []
    p = px
    for i in range(n):
        o = p
        c = p + (1 if i % 3 else -0.5)
        h = max(o, c) + 0.4
        l_ = min(o, c) - 0.4
        bars.append(
            {
                "time": start + i * 300,
                "open": o,
                "high": h,
                "low": l_,
                "close": c,
                "volume": 1000 + i * 10,
                "oi": 5000 + i,
            }
        )
        p = c
    return bars


class TestIndicators(unittest.TestCase):
    def test_ema_rsi_macd_vwap(self):
        bars = _synth_bars()
        ribbon = ema_ribbon(bars)
        self.assertIn("ema9", ribbon)
        self.assertIn("ema200", ribbon)
        self.assertGreater(len(ribbon["ema9"]), 0)
        rsi = rsi_series(bars)
        self.assertGreater(len(rsi), 10)
        self.assertTrue(all(0 <= p["value"] <= 100 for p in rsi))
        macd = macd_series(bars)
        self.assertGreater(len(macd["macd"]), 0)
        self.assertEqual(len(macd["macd"]), len(macd["signal"]))
        vwap = compute_session_vwap_bands(bars)
        self.assertIsNotNone(vwap)
        self.assertGreater(vwap["vwap"], 0)
        self.assertGreaterEqual(vwap["band_2_upper"], vwap["band_1_upper"])


class TestChartApi(unittest.TestCase):
    def test_chart_routes_and_daily_payload(self):
        from fastapi.testclient import TestClient

        from app.main import APP_VERSION, app

        self.assertTrue(
            APP_VERSION.startswith("4.4")
            or APP_VERSION.startswith("5."),
            APP_VERSION,
        )
        client = TestClient(app)
        r = client.get("/api/chart/RELIANCE", params={"interval": "1d", "days": 60})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["interval"], "1d")
        self.assertIn("ema_ribbon", body)
        self.assertIn("previous_day", body)
        self.assertFalse(body.get("demo", False))
        # live endpoint
        r2 = client.get("/api/chart/RELIANCE/live", params={"interval": "1d"})
        self.assertEqual(r2.status_code, 200)
        self.assertIn("ltp", r2.json())

    def test_invalid_interval(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        r = client.get("/api/chart/RELIANCE", params={"interval": "3m"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
