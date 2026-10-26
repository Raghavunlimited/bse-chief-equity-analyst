"""Phase 6 — chart correctness, freshness, optional depth/options honesty."""
from __future__ import annotations

import os
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ.setdefault("EOD_INGEST_SCHEDULE_ENABLED", "false")

from app.chart_data import (  # noqa: E402
    _bars_from_yahoo,
    _freshness_for_bars,
    build_chart_payload,
    ema_ribbon,
    rsi_series,
)
from app.strategy.index_core import ema as strategy_ema  # noqa: E402
from app.strategy.index_core import rsi as strategy_rsi  # noqa: E402


def _synth_bars(n=80, start=None, px=100.0, step=300):
    start = int(start if start is not None else time.time() - n * step)
    bars = []
    p = px
    for i in range(n):
        o = p
        c = p + (1 if i % 3 else -0.5)
        h = max(o, c) + 0.4
        l_ = min(o, c) - 0.4
        bars.append(
            {
                "time": start + i * step,
                "open": o,
                "high": h,
                "low": l_,
                "close": c,
                "volume": 1000 + i * 10,
                "oi": None,
            }
        )
        p = c
    return bars


class YahooParseTests(unittest.TestCase):
    def test_missing_bars_skipped_not_filled(self):
        data = {
            "timestamp": [100, 200, 300],
            "indicators": {
                "quote": [
                    {
                        "open": [1.0, None, 3.0],
                        "high": [1.1, None, 3.1],
                        "low": [0.9, None, 2.9],
                        "close": [1.05, None, 3.05],
                        "volume": [10, 20, 30],
                    }
                ]
            },
        }
        bars, missing = _bars_from_yahoo(data)
        self.assertEqual(missing, 1)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]["time"], 100)
        self.assertEqual(bars[1]["time"], 300)
        # No synthetic middle bar
        self.assertNotIn(200, [b["time"] for b in bars])


class FreshnessTests(unittest.TestCase):
    def test_fresh_intraday(self):
        bars = _synth_bars(5, start=int(time.time()) - 4 * 300)
        f = _freshness_for_bars(bars, interval="5m")
        self.assertIn(f["status"], ("ok", "aging"))
        self.assertEqual(f["timezone"], "Asia/Kolkata")
        self.assertIn("last_bar_ist", f)

    def test_stale_intraday(self):
        bars = _synth_bars(3, start=1_600_000_000)
        f = _freshness_for_bars(bars, interval="5m")
        self.assertEqual(f["status"], "stale")
        self.assertEqual(f["label"], "STALE")

    def test_empty_unavailable(self):
        f = _freshness_for_bars([], interval="1d")
        self.assertEqual(f["status"], "unavailable")


class StrategyAgreementTests(unittest.TestCase):
    def test_ema_matches_index_core(self):
        bars = _synth_bars(60)
        closes = [float(b["close"]) for b in bars]
        ribbon = ema_ribbon(bars)
        for period in (9, 21, 50):
            expected = strategy_ema(closes, period)
            self.assertIsNotNone(expected)
            last = ribbon[f"ema{period}"][-1]["value"]
            self.assertAlmostEqual(last, expected, places=4)

    def test_rsi_same_closes_different_formula_documented(self):
        """Desk RSI ≠ Wilder chart RSI, but both consume identical closes."""
        bars = _synth_bars(40)
        closes = [float(b["close"]) for b in bars]
        chart = rsi_series(bars)
        desk = strategy_rsi(closes, 14)
        self.assertIsNotNone(desk)
        self.assertGreater(len(chart), 0)
        # Both in [0, 100]; formulas may diverge — not asserted equal
        self.assertTrue(0 <= desk <= 100)
        self.assertTrue(0 <= chart[-1]["value"] <= 100)


class PayloadHonestyTests(unittest.TestCase):
    def test_empty_payload_marks_unavailable(self):
        with patch("app.chart_data._bars_from_eod", return_value=[]):
            with patch("app.chart_data._fetch_yahoo_chart", return_value=None):
                with patch("app.chart_data._walls_for", return_value=None):
                    with patch("app.chart_data.previous_day_levels", return_value=None):
                        p = build_chart_payload("NOSUCH", interval="1d", limit=60)
        self.assertFalse(p["has_data"])
        self.assertEqual(p["status"], "unavailable")
        self.assertEqual(p["bars"], [])
        self.assertIsNone(p["walls"])
        self.assertFalse(p["optional_features"]["walls"]["available"])
        self.assertFalse(p["optional_features"]["depth_l2"]["available"])
        self.assertFalse(p["optional_features"]["pcr"]["available"])
        self.assertIn("timezone", p)
        self.assertEqual(p["timezone"]["display_timezone"], "Asia/Kolkata")
        self.assertFalse(p.get("demo", True))

    def test_daily_from_eod_has_price_kind_and_source(self):
        eod = [
            {
                "time": f"2026-10-{d:02d}",
                "open": 100 + d,
                "high": 101 + d,
                "low": 99 + d,
                "close": 100.5 + d,
                "volume": 1000,
                "oi": None,
            }
            for d in range(1, 40)
        ]
        with patch("app.chart_data._bars_from_eod", return_value=eod):
            with patch("app.chart_data._walls_for", return_value=None):
                with patch(
                    "app.chart_data.previous_day_levels",
                    return_value={"date": "2026-10-39", "high": 1, "low": 1, "close": 1, "open": 1},
                ):
                    p = build_chart_payload("RELIANCE", interval="1d", limit=60)
        self.assertTrue(p["has_data"])
        self.assertEqual(p["source"], "kotak_eod_db")
        self.assertEqual(p["price_kind"], "eod_close")
        self.assertEqual(p["interval"], "1d")
        self.assertEqual(p["range"]["returned_bars"], len(eod))
        self.assertEqual(p["ltp"], eod[-1]["close"])
        self.assertIn("ema_ribbon", p)
        self.assertFalse(p["optional_features"]["walls"]["available"])

    def test_walls_only_when_verified_analytics(self):
        bars = _synth_bars(30, start=int(time.time()) - 29 * 300)
        walls = {"call_wall": 100, "put_wall": 90, "max_pain": 95, "expiry": "2026-11-01", "atm": 95}
        with patch("app.chart_data._YAHOO", {"5m": ("5m", "5d")}):
            with patch("app.chart_data._fetch_yahoo_chart") as fy:
                # Force path through merge of synthetic via mock yahoo parse
                fy.return_value = {
                    "timestamp": [b["time"] for b in bars],
                    "indicators": {
                        "quote": [
                            {
                                "open": [b["open"] for b in bars],
                                "high": [b["high"] for b in bars],
                                "low": [b["low"] for b in bars],
                                "close": [b["close"] for b in bars],
                                "volume": [b["volume"] for b in bars],
                            }
                        ]
                    },
                }
                with patch("app.chart_data._merge_live_bars", side_effect=lambda s, i, b: b):
                    with patch("app.chart_data._walls_for", return_value=walls):
                        with patch("app.chart_data.previous_day_levels", return_value=None):
                            p = build_chart_payload("NIFTY", interval="5m", limit=40)
        self.assertTrue(p["optional_features"]["walls"]["available"])
        self.assertEqual(p["walls"]["call_wall"], 100)
        self.assertEqual(p["price_kind"], "intraday_bar_close")
        self.assertIn("yahoo_range", p["range"])


class DepthAndOptionApiTests(unittest.TestCase):
    def test_depth_unavailable_when_no_book(self):
        from fastapi.testclient import TestClient

        import re

        from app.main import APP_VERSION, app

        # Phase-6 lineage: major 5, minor ≥ 6
        m = re.match(r"^5\.(\d+)\.", APP_VERSION)
        self.assertTrue(m and int(m.group(1)) >= 6, APP_VERSION)
        hub = MagicMock()
        hub.get_book.return_value = None
        q = MagicMock()
        q.ltp = 100.0
        q.symbol = "RELIANCE"
        hub.get_quote.return_value = q
        with patch("app.kotak.feed_hub.get_feed_hub", return_value=hub):
            c = TestClient(app)
            r = c.get("/api/kotak/feed/depth/nse_cm|123")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["status"], "unavailable")
        self.assertIsNone(body["bids"])
        self.assertIsNone(body["asks"])

    def test_option_chain_status_unavailable_idle(self):
        from fastapi.testclient import TestClient

        from app.main import app

        eng = MagicMock()
        eng.status.return_value = {"active": False, "underlying": "NIFTY"}
        with patch(
            "app.kotak.option_chain.get_option_chain_engine", return_value=eng
        ):
            c = TestClient(app)
            r = c.get("/api/kotak/option-chain/status", params={"underlying": "NIFTY"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["status"], "unavailable")
        self.assertFalse(body["verified_in_ci"])

    def test_chart_api_honesty_fields(self):
        from fastapi.testclient import TestClient

        from app.main import app

        eod = [
            {
                "time": f"2026-09-{d:02d}",
                "open": 10 + d,
                "high": 11 + d,
                "low": 9 + d,
                "close": 10.5 + d,
                "volume": 100,
                "oi": None,
            }
            for d in range(1, 28)
        ]
        with patch("app.chart_data._bars_from_eod", return_value=eod):
            with patch("app.chart_data._walls_for", return_value=None):
                with patch("app.chart_data.previous_day_levels", return_value=None):
                    c = TestClient(app)
                    r = c.get("/api/chart/RELIANCE", params={"interval": "1d", "days": 60})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("freshness", body)
        self.assertIn("optional_features", body)
        self.assertIn("timezone", body)
        self.assertNotIn("walls", body.get("overlays") or [])
        self.assertEqual(body["price_kind"], "eod_close")
        # live
        with patch("app.chart_data.build_chart_payload") as bcp:
            bcp.return_value = {
                "bars": eod[-3:],
                "ltp": eod[-1]["close"],
                "walls": None,
                "optional_features": {"walls": {"available": False}},
                "freshness": {"status": "ok"},
                "status": "ok",
                "source": "kotak_eod_db",
                "price_kind": "eod_close",
                "has_data": True,
            }
            r2 = c.get("/api/chart/RELIANCE/live", params={"interval": "1d"})
        self.assertEqual(r2.status_code, 200)
        self.assertIn("ltp_source", r2.json())


if __name__ == "__main__":
    unittest.main()
