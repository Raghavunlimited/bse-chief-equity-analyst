"""Options OI visualization — normalization, unavailable, freshness, API."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ.setdefault("BIND_HOST", "127.0.0.1")
os.environ.setdefault("EOD_INGEST_SCHEDULE_ENABLED", "false")

from app.options_oi import (  # noqa: E402
    FIELD_SEMANTICS,
    _normalize_leg,
    build_oi_visualization,
    unavailable_payload,
)


def _leg(
    *,
    oi=1000.0,
    oi_change=50.0,
    volume=200.0,
    iv=0.18,
    iv_pct=18.0,
    age=1.0,
    ltp=120.0,
    greeks_ok=True,
    error=None,
):
    return {
        "ltp": ltp,
        "oi": oi,
        "oi_change": oi_change,
        "volume": volume,
        "iv": iv,
        "iv_pct": iv_pct,
        "quote_age_sec": age,
        "feed_status": "LIVE",
        "greeks_ok": greeks_ok,
        "trading_symbol": "TEST",
        "buildup": {"label": "Long Buildup"},
        "error": error,
    }


class NormalizeTests(unittest.TestCase):
    def test_missing_leg(self):
        n = _normalize_leg(None, "CE")
        self.assertFalse(n["available"])
        self.assertFalse(n["oi"]["available"])
        self.assertEqual(n["freshness"]["status"], "unavailable")

    def test_present_fields(self):
        n = _normalize_leg(_leg(), "CE")
        self.assertTrue(n["oi"]["available"])
        self.assertEqual(n["oi"]["value"], 1000.0)
        self.assertEqual(n["oi_change"]["value"], 50.0)
        self.assertEqual(n["volume"]["value"], 200.0)
        self.assertEqual(n["iv_pct"]["value"], 18.0)
        self.assertEqual(n["freshness"]["label"], "FRESH")
        self.assertEqual(n["oi"]["semantic"], FIELD_SEMANTICS["oi"])

    def test_stale_leg(self):
        n = _normalize_leg(_leg(age=120.0), "PE")
        self.assertEqual(n["freshness"]["status"], "stale")

    def test_null_oi_not_invented(self):
        n = _normalize_leg(_leg(oi=None, oi_change=None), "CE")
        self.assertFalse(n["oi"]["available"])
        self.assertIsNone(n["oi"]["value"])

    def test_failed_greeks_iv_unavailable(self):
        n = _normalize_leg(_leg(iv=None, iv_pct=None, greeks_ok=False), "CE")
        self.assertFalse(n["iv"]["available"])


class UnavailablePayloadTests(unittest.TestCase):
    def test_inactive_shape(self):
        with patch("app.options_oi._list_expiries_catalog") as cat:
            cat.return_value = {
                "available": True,
                "expiries": ["2026-11-03", "2026-11-10"],
                "nearest": "2026-11-03",
                "weekly": "2026-11-03",
                "monthly": "2026-11-25",
                "oi_for_listed_expiries": "only_after_activate_for_expiry",
                "reason": None,
            }
            p = unavailable_payload(
                "NIFTY",
                reason="option_chain_inactive",
                blocker="need activate",
            )
        self.assertFalse(p["available"])
        self.assertEqual(p["status"], "unavailable")
        self.assertFalse(p["provider_e2e_verified_in_ci"])
        self.assertEqual(len(p["expiries_oi_comparison"]), 2)
        self.assertFalse(p["expiries_oi_comparison"][0]["oi_available"])
        self.assertIsNone(p["expiries_oi_comparison"][0]["call_oi_total"])
        self.assertIn("not standalone trading signals", p["signal_disclaimer"])
        self.assertFalse(p.get("demo", True))


class BuildVizTests(unittest.TestCase):
    def test_inactive_returns_unavailable(self):
        eng = MagicMock()
        eng.status.return_value = {"active": False, "underlying": "NIFTY"}
        with patch("app.kotak.option_chain.get_option_chain_engine", return_value=eng):
            with patch("app.options_oi._list_expiries_catalog", return_value={"expiries": []}):
                out = build_oi_visualization("NIFTY")
        self.assertFalse(out["available"])
        self.assertIn("activate", out["blocker"].lower())

    def test_active_snapshot_normalized(self):
        eng = MagicMock()
        eng.status.return_value = {"active": True, "underlying": "NIFTY"}
        eng.snapshot.return_value = {
            "underlying": "NIFTY",
            "expiry": "2026-11-03",
            "spot": 24500.0,
            "atm": 24500.0,
            "wing": 2,
            "subscribed": 8,
            "source": "kotak_neo_ws",
            "as_of": "2026-10-26T10:00:00+00:00",
            "rows": [
                {
                    "strike": 24400.0,
                    "atm": False,
                    "ce": _leg(oi=5000, age=2),
                    "pe": _leg(oi=4000, age=2),
                },
                {
                    "strike": 24500.0,
                    "atm": True,
                    "ce": _leg(oi=8000, age=2),
                    "pe": _leg(oi=9000, age=2),
                },
                {
                    "strike": 24600.0,
                    "atm": False,
                    "ce": _leg(oi=None, volume=None, iv=None, iv_pct=None, error="no_live_quote"),
                    "pe": _leg(oi=3000, age=2),
                },
            ],
        }
        with patch("app.kotak.option_chain.get_option_chain_engine", return_value=eng):
            with patch(
                "app.options_oi._list_expiries_catalog",
                return_value={
                    "available": True,
                    "expiries": ["2026-11-03", "2026-11-10"],
                    "nearest": "2026-11-03",
                    "weekly": "2026-11-03",
                    "monthly": None,
                    "oi_for_listed_expiries": "only_after_activate_for_expiry",
                    "reason": None,
                },
            ):
                out = build_oi_visualization("NIFTY")
        self.assertTrue(out["available"])
        self.assertEqual(out["active_expiry"], "2026-11-03")
        self.assertEqual(len(out["series"]), 3)
        self.assertTrue(out["series"][1]["atm"])
        self.assertFalse(out["series"][2]["call"]["oi"]["available"])
        self.assertTrue(out["series"][2]["put"]["oi"]["available"])
        self.assertEqual(out["totals"]["call_oi"], 13000.0)
        self.assertEqual(out["totals"]["put_oi"], 16000.0)
        self.assertIsNotNone(out["totals"]["pcr"])
        # Cross-expiry: only active has OI totals
        by_exp = {e["expiry"]: e for e in out["expiries_oi_comparison"]}
        self.assertTrue(by_exp["2026-11-03"]["oi_available"])
        self.assertFalse(by_exp["2026-11-10"]["oi_available"])
        self.assertIsNone(by_exp["2026-11-10"]["call_oi_total"])
        self.assertEqual(out["source"], "kotak_neo_ws")
        self.assertTrue(out["underlying_price"]["available"])


class ApiIntegrationTests(unittest.TestCase):
    def test_oi_viz_endpoint_inactive(self):
        from fastapi.testclient import TestClient

        from app.main import APP_VERSION, app

        self.assertTrue(
            "options-oi" in APP_VERSION
            or "trade-journal" in APP_VERSION
            or "position-sizing" in APP_VERSION
            or "market-events" in APP_VERSION
            or "strategy-eval" in APP_VERSION
            or APP_VERSION.startswith("5.8")
            or APP_VERSION.startswith("5.9")
            or APP_VERSION.startswith("5.10")
            or APP_VERSION.startswith("5.11")
            or APP_VERSION.startswith("5.12"),
            APP_VERSION,
        )
        eng = MagicMock()
        eng.status.return_value = {"active": False}
        with patch("app.kotak.option_chain.get_option_chain_engine", return_value=eng):
            with patch(
                "app.options_oi._list_expiries_catalog",
                return_value={"expiries": ["2026-11-03"], "available": True},
            ):
                c = TestClient(app)
                r = c.get("/api/kotak/option-chain/NIFTY/oi-viz")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["status"], "unavailable")
        self.assertIn("field_semantics", body)

    def test_oi_viz_matches_active_normalization(self):
        from fastapi.testclient import TestClient

        from app.main import app

        eng = MagicMock()
        eng.status.return_value = {"active": True}
        eng.snapshot.return_value = {
            "underlying": "BANKNIFTY",
            "expiry": "2026-11-03",
            "spot": 52000.0,
            "atm": 52000.0,
            "wing": 1,
            "subscribed": 4,
            "source": "kotak_neo_ws",
            "as_of": "2026-10-26T10:00:00+00:00",
            "rows": [
                {
                    "strike": 52000.0,
                    "atm": True,
                    "ce": _leg(oi=100, age=1),
                    "pe": _leg(oi=150, age=1),
                }
            ],
        }
        with patch("app.kotak.option_chain.get_option_chain_engine", return_value=eng):
            with patch(
                "app.options_oi._list_expiries_catalog",
                return_value={"expiries": ["2026-11-03"], "available": True},
            ):
                c = TestClient(app)
                r = c.get("/api/kotak/option-chain/BANKNIFTY/oi-viz")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["available"])
        self.assertEqual(body["call_oi_by_strike"][0]["oi"], 100)
        self.assertEqual(body["put_oi_by_strike"][0]["oi"], 150)
        # Consistency: series OI == by_strike OI
        self.assertEqual(
            body["series"][0]["call"]["oi"]["value"],
            body["call_oi_by_strike"][0]["oi"],
        )


if __name__ == "__main__":
    unittest.main()
