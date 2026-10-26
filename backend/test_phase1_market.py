"""Phase 1: EOD vs LTP types, IST session clock, truthful LIVE vs FALLBACK, stale safety."""
from __future__ import annotations

import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ["LIVE_QUOTE_STALE_SEC"] = "5"

from app.market_session import (  # noqa: E402
    annotate_live_quote,
    assess_quote_age,
    build_feed_health,
    classify_market_data_state,
    freeze_live_sides,
    session_snapshot,
)
from app.market_types import (  # noqa: E402
    EODBar,
    IntradayBar,
    LiveQuote,
    provenance_for_state,
    provider_class_for_source,
)

IST = ZoneInfo("Asia/Kolkata")


class TypeHygieneTests(unittest.TestCase):
    def test_eod_bar_price_kind(self):
        bar = EODBar(
            symbol="RELIANCE",
            trade_date="2026-10-23",
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=100.0,
            source="kotak",
        )
        self.assertEqual(bar.price_kind, "eod_close")
        d = bar.to_dict()
        self.assertEqual(d["price_kind"], "eod_close")
        self.assertEqual(d["market_data_state"], "EOD")
        self.assertEqual(d["provenance"], "eod")
        self.assertFalse(d["is_current_live"])

    def test_intraday_bar_contract(self):
        b = IntradayBar(
            symbol="NIFTY",
            bar_start_unix=1_700_000_000.0,
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=10,
            source="yahoo_chart",
        )
        d = b.to_dict()
        self.assertEqual(d["timeframe"], "5m")
        self.assertFalse(d["is_current_live"])

    def test_yahoo_age_fresh_is_fallback_not_live_provenance(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        q = LiveQuote(
            symbol="RELIANCE",
            ltp=1200.0,
            quote_ts_unix=now - 1.0,
            fetched_at_unix=now,
            age_sec=1.0,
            feed_status="LIVE",  # age-bucket before classify
            source="yahoo_chart",
        )
        q = annotate_live_quote(q, now_unix=now, session=sess)
        d = q.to_dict()
        self.assertEqual(q.market_data_state, "FALLBACK")
        self.assertEqual(d["provenance"], "fallback")
        self.assertFalse(d["is_current_live"])
        self.assertEqual(d["provider_class"], "research_fallback")

    def test_kotak_age_fresh_is_broker_live(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        q = LiveQuote(
            symbol="RELIANCE",
            ltp=1200.0,
            quote_ts_unix=now - 1.0,
            fetched_at_unix=now,
            age_sec=1.0,
            feed_status="LIVE",
            source="kotak_neo_ws",
        )
        q = annotate_live_quote(q, now_unix=now, session=sess)
        d = q.to_dict()
        self.assertEqual(q.market_data_state, "LIVE")
        self.assertEqual(d["provenance"], "live")
        self.assertTrue(d["is_current_live"])


class SessionTests(unittest.TestCase):
    def test_weekday_regular(self):
        at = datetime(2026, 10, 26, 10, 0, tzinfo=IST)
        s = session_snapshot(at)
        self.assertTrue(s["in_regular_hours"])
        self.assertEqual(s["session_label"], "REGULAR")
        self.assertTrue(s["holiday_calendar_applied"])
        self.assertIn("holiday", s["calendar_note"].lower())

    def test_weekday_post(self):
        at = datetime(2026, 10, 26, 16, 0, tzinfo=IST)
        s = session_snapshot(at)
        self.assertFalse(s["in_regular_hours"])
        self.assertEqual(s["session_label"], "POST-MARKET")

    def test_weekday_pre(self):
        at = datetime(2026, 10, 26, 9, 5, tzinfo=IST)
        s = session_snapshot(at)
        self.assertEqual(s["session_label"], "PRE-MARKET")
        self.assertFalse(s["in_regular_hours"])

    def test_weekend_not_regular(self):
        at = datetime(2026, 10, 25, 11, 0, tzinfo=IST)  # Sunday
        s = session_snapshot(at)
        self.assertEqual(s["session_label"], "WEEKEND")
        self.assertFalse(s["in_regular_hours"])


class StaleGateTests(unittest.TestCase):
    def test_stale_during_regular(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        status, age, allowed = assess_quote_age(now - 6.0, now_unix=now, session=sess)
        self.assertEqual(status, "STALE")
        self.assertFalse(allowed)
        self.assertGreater(age, 5.0)

    def test_classify_yahoo_stale(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        state, age, gen, broker = classify_market_data_state(
            source="yahoo_chart",
            quote_ts_unix=now - 10.0,
            has_ltp=True,
            now_unix=now,
            session=sess,
        )
        self.assertEqual(state, "STALE")
        self.assertFalse(gen)
        self.assertFalse(broker)

    def test_live_during_regular_age_ok(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        status, age, allowed = assess_quote_age(now - 1.0, now_unix=now, session=sess)
        self.assertEqual(status, "LIVE")
        self.assertTrue(allowed)

    def test_freeze_sides_marks_last_observation_not_live(self):
        rows = freeze_live_sides(
            [
                {
                    "symbol": "X",
                    "side": "BUY",
                    "score": 80,
                    "confidence": 75,
                    "thesis": "up",
                    "tags": [],
                    "price": 100.0,
                    "source": "yahoo_chart",
                    "quote_age_sec": 12.0,
                    "badge": "STRONG_BUY",
                },
                {"symbol": "Y", "side": "LONG", "score": 70, "thesis": "up", "tags": []},
            ],
            "STALE",
            market_data_state="STALE",
        )
        self.assertEqual(rows[0]["side"], "HOLD")
        self.assertEqual(rows[1]["side"], "FLAT")
        self.assertIn("FEED_HALT", rows[0]["tags"])
        self.assertIn("LAST_OBSERVATION", rows[0]["tags"])
        self.assertFalse(rows[0]["is_current_live"])
        self.assertTrue(rows[0]["is_last_observation"])
        self.assertEqual(rows[0]["signal_generation"], "halted")
        self.assertEqual(rows[0]["badge"], "HOLD")
        self.assertEqual(rows[0]["observation"]["price"], 100.0)
        self.assertFalse(rows[0]["observation"]["is_current_live"])
        self.assertLessEqual(rows[0]["confidence"], 40.0)

    def test_feed_health_yahoo_fallback_not_broker_live(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        q = annotate_live_quote(
            LiveQuote(
                symbol="NIFTY",
                ltp=22600.0,
                quote_ts_unix=now - 1.0,
                fetched_at_unix=now,
                age_sec=1.0,
                feed_status="LIVE",
                source="yahoo_chart",
            ),
            now_unix=now,
            session=sess,
        )
        h = build_feed_health([q], session=sess)
        self.assertTrue(h.live_calls_allowed)
        self.assertFalse(h.broker_live)
        self.assertEqual(h.market_data_state, "FALLBACK")
        self.assertEqual(h.quotes_fallback, 1)

    def test_feed_health_halts_when_stale(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        q = annotate_live_quote(
            LiveQuote(
                symbol="NIFTY",
                ltp=22600.0,
                quote_ts_unix=now - 10.0,
                fetched_at_unix=now,
                age_sec=10.0,
                feed_status="STALE",
                source="yahoo_chart",
            ),
            now_unix=now,
            session=sess,
        )
        h = build_feed_health([q], session=sess)
        self.assertFalse(h.live_calls_allowed)
        self.assertEqual(h.feed_status, "STALE")


class ProviderHelperTests(unittest.TestCase):
    def test_provider_class(self):
        self.assertEqual(provider_class_for_source("kotak_neo_ws"), "broker")
        self.assertEqual(provider_class_for_source("yahoo_chart"), "research_fallback")
        self.assertEqual(provenance_for_state("FALLBACK"), "fallback")
        self.assertEqual(provenance_for_state("LIVE"), "live")


class HealthApiContractTests(unittest.TestCase):
    def test_health_vs_ready_fields(self):
        from fastapi.testclient import TestClient

        from app.main import APP_VERSION, app

        self.assertTrue(APP_VERSION.startswith("5."))
        c = TestClient(app)
        h = c.get("/api/health")
        self.assertEqual(h.status_code, 200)
        body = h.json()
        self.assertTrue(body.get("liveness"))
        self.assertIn("live_quotes", body["feeds"])
        self.assertIsInstance(body["feeds"]["live_quotes"], dict)
        self.assertIn("research_fallback_source", body["feeds"]["live_quotes"])
        self.assertIn("calendar_note", body)

        sess = c.get("/api/market/session")
        self.assertEqual(sess.status_code, 200)
        self.assertIn("calendar_note", sess.json())
        self.assertIn("holiday_calendar_applied", sess.json())


if __name__ == "__main__":
    unittest.main()
