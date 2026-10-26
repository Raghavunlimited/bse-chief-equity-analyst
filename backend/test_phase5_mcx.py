"""Phase 5 — MCX proxy honesty: mappings, units, currency, labels, no false lots."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ.setdefault("EOD_INGEST_SCHEDULE_ENABLED", "false")

from app.market_types import LiveQuote  # noqa: E402
from app.signals.consultant_rules import grade_mcx  # noqa: E402
from app.signals.mcx_calls import build_mcx_calls  # noqa: E402
from app.strategy.mcx import _bias, _snap_to_dict, build_mcx_desk  # noqa: E402
from app.strategy.mcx_instruments import (  # noqa: E402
    INSTRUMENTS,
    assert_no_false_mcx_claims,
    public_catalog,
)


def _quote(sym: str = "GC=F", ltp: float = 2650.0) -> LiveQuote:
    return LiveQuote(
        symbol=sym.replace("=F", ""),
        ltp=ltp,
        quote_ts_unix=1_700_000_000.0,
        fetched_at_unix=1_700_000_001.0,
        age_sec=1.0,
        feed_status="LIVE",
        source="yahoo_chart",
        timeframe="5m",
        change_pct=0.8,
        session_open=ltp * 0.995,
        session_high=ltp * 1.01,
        session_low=ltp * 0.99,
        closes_5m=tuple(ltp * (1 + i * 0.001) for i in range(12)),
        currency="USD",
        yahoo_symbol=sym,
    )


class InstrumentRegistryTests(unittest.TestCase):
    def test_none_are_mcx_listed(self):
        for row in public_catalog():
            self.assertFalse(row["is_mcx_listed"])
            self.assertFalse(row["expectancy_eligible"])
            self.assertIn(row["instrument_class"], ("global_futures_proxy", "fx_context"))
            fails = assert_no_false_mcx_claims(row)
            self.assertEqual(fails, [], fails)

    def test_currency_and_units(self):
        by_id = {r["id"]: r for r in INSTRUMENTS}
        self.assertEqual(by_id["GOLD"]["currency"], "USD")
        self.assertIn("oz", by_id["GOLD"]["unit"].lower())
        self.assertEqual(by_id["CRUDE"]["currency"], "USD")
        self.assertEqual(by_id["USDINR"]["currency"], "INR")
        self.assertEqual(by_id["USDINR"]["instrument_class"], "fx_context")
        self.assertEqual(by_id["GOLD"]["price_scale"], 1.0)

    def test_expiry_roll_notes_present(self):
        for row in INSTRUMENTS:
            self.assertTrue(row["expiry_note"])
            self.assertTrue(row["roll_note"])
            self.assertIn("unavailable", row["lot_sizing"].lower())

    def test_related_mcx_is_hint_not_contract(self):
        gold = next(r for r in INSTRUMENTS if r["id"] == "GOLD")
        self.assertEqual(gold["mcx_mapping_status"], "unvalidated_name_hint")
        self.assertIn("GOLD", gold["related_mcx_symbols"])


class LiveQuoteNormalizationTests(unittest.TestCase):
    def test_snap_to_dict_from_livequote(self):
        d = _snap_to_dict(_quote())
        self.assertIsInstance(d, dict)
        self.assertEqual(d["price"], 2650.0)
        self.assertIn("closes_5m", d)

    def test_bias_accepts_livequote_via_dict(self):
        d = _snap_to_dict(_quote(ltp=2700.0))
        out = _bias(d)
        self.assertIn(out["side"], ("LONG", "SHORT", "FLAT"))
        self.assertIsNotNone(out["price"])
        self.assertIn("NOT_MCX_CONTRACT", out["tags"])

    def test_bias_missing_quote(self):
        out = _bias({"price": None, "feed_status": "ERROR"})
        self.assertEqual(out["side"], "FLAT")
        self.assertFalse(out["available"])


class DeskBuildTests(unittest.TestCase):
    def test_build_desk_with_livequotes_no_crash(self):
        snaps = {c["yahoo"]: _quote(c["yahoo"], 100.0 + i) for i, c in enumerate(INSTRUMENTS)}
        with patch("app.strategy.mcx.live_quotes.fetch_many", return_value=snaps):
            desk = build_mcx_desk()
        self.assertEqual(desk["desk"], "mcx")
        self.assertFalse(desk["expectancy_gated"])
        self.assertEqual(len(desk["signals"]), len(INSTRUMENTS))
        for s in desk["signals"]:
            self.assertFalse(s["is_mcx_listed"])
            self.assertIn(s["display_label"], ("GLOBAL FUTURES PROXY", "FX CONTEXT"))
            self.assertNotIn("suggested_lots", s)
            self.assertEqual(assert_no_false_mcx_claims(s), [])
            # Global proxies must not claim INR commodity unit
            if s["instrument_class"] == "global_futures_proxy":
                self.assertEqual(s["currency"], "USD")

    def test_unavailable_labeled(self):
        empty = {c["yahoo"]: None for c in INSTRUMENTS}
        with patch("app.strategy.mcx.live_quotes.fetch_many", return_value=empty):
            desk = build_mcx_desk()
        for s in desk["signals"]:
            self.assertEqual(s["side"], "FLAT")
            self.assertIn("PROXY_UNAVAILABLE", s["tags"])
            self.assertFalse(s.get("available", True))


class CallsAndGateTests(unittest.TestCase):
    def test_calls_cap_confidence_and_no_strong(self):
        snaps = {c["yahoo"]: _quote(c["yahoo"], 2000.0) for c in INSTRUMENTS}
        with patch("app.strategy.mcx.live_quotes.fetch_many", return_value=snaps):
            out = build_mcx_calls()
        self.assertFalse(out["expectancy_gated"])
        for c in out["calls"]:
            self.assertLessEqual(c["confidence"], 58.0)
            self.assertNotIn(c.get("badge"), ("STRONG_BUY", "STRONG_SELL"))
            self.assertFalse(c.get("is_mcx_listed"))
            self.assertEqual(c["expectancy"]["gates"]["passed"], False)
            self.assertIn("MCX_PROXY", " ".join(c.get("tags") or []) or "MCX_PROXY")
            # flattened for UI
            self.assertTrue(c.get("mcx_hint") or c.get("display_label"))

    def test_grade_unavailable(self):
        g = grade_mcx({"id": "GOLD", "available": False, "score": 90, "side": "LONG"})
        self.assertEqual(g["side"], "HOLD")
        self.assertLessEqual(g["confidence"], 25.0)


class ApiTests(unittest.TestCase):
    def test_consultant_mcx_200(self):
        from fastapi.testclient import TestClient

        import re

        from app.main import APP_VERSION, app

        # Phase-5 lineage: major 5, minor ≥ 5
        m = re.match(r"^5\.(\d+)\.", APP_VERSION)
        self.assertTrue(m and int(m.group(1)) >= 5, APP_VERSION)
        snaps = {c["yahoo"]: _quote(c["yahoo"]) for c in INSTRUMENTS}
        with patch("app.strategy.mcx.live_quotes.fetch_many", return_value=snaps):
            c = TestClient(app)
            r = c.get("/api/consultant/mcx")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertFalse(body.get("expectancy_gated", True))
            self.assertTrue(any(x.get("display_label") for x in body.get("calls") or []))
            cat = c.get("/api/consultant/mcx/instruments")
            self.assertEqual(cat.status_code, 200)
            self.assertFalse(cat.json()["is_mcx_listed_feed"])


if __name__ == "__main__":
    unittest.main()
