"""Phase 4 — holiday calendar, trading-day freshness, scheduler gates, journal idempotency."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ["EOD_INGEST_SCHEDULE_ENABLED"] = "false"
os.environ["EOD_INGEST_HOUR_IST"] = "18"
os.environ["EOD_INGEST_MINUTE_IST"] = "45"
os.environ["EOD_SETTLE_HOUR_IST"] = "18"
os.environ["EOD_SETTLE_MINUTE_IST"] = "30"

IST = ZoneInfo("Asia/Kolkata")


class CalendarTests(unittest.TestCase):
    def setUp(self):
        from app.nse_calendar import clear_calendar_cache

        clear_calendar_cache()

    def test_weekend_not_trading(self):
        from app.nse_calendar import is_trading_day

        self.assertFalse(is_trading_day(date(2026, 10, 24)))  # Saturday
        self.assertFalse(is_trading_day(date(2026, 10, 25)))  # Sunday
        self.assertTrue(is_trading_day(date(2026, 10, 26)))  # Monday (not in holiday list)

    def test_configured_holiday(self):
        from app.nse_calendar import is_holiday, is_trading_day

        # Independence Day 2025 — in snapshot
        self.assertTrue(is_holiday(date(2025, 8, 15)))
        self.assertFalse(is_trading_day(date(2025, 8, 15)))

    def test_previous_trading_day_skips_holiday_weekend(self):
        from app.nse_calendar import previous_trading_day

        # 2025-08-16 is Saturday after Friday Independence Day holiday
        # Fri 15 Aug holiday, Sat 16, Sun 17 → previous from Mon 18 is Thu 14
        self.assertEqual(previous_trading_day(date(2025, 8, 18)), date(2025, 8, 14))

    def test_expected_eod_before_and_after_settle(self):
        from app.nse_calendar import expected_eod_as_of

        # Trading Monday 2026-10-26
        before = datetime(2026, 10, 26, 12, 0, tzinfo=IST)
        after = datetime(2026, 10, 26, 19, 0, tzinfo=IST)
        # Oct 26 2026 Monday — before settle → previous trading day Fri Oct 23
        self.assertEqual(expected_eod_as_of(before), date(2026, 10, 23))
        self.assertEqual(expected_eod_as_of(after), date(2026, 10, 26))

    def test_session_snapshot_holiday(self):
        from app.market_session import session_snapshot

        # Fixed holiday date — not "today"
        at = datetime(2025, 8, 15, 11, 0, tzinfo=IST)
        s = session_snapshot(at)
        self.assertEqual(s["session_label"], "HOLIDAY")
        self.assertFalse(s["in_regular_hours"])
        self.assertTrue(s["holiday_calendar_applied"])


class FreshnessTests(unittest.TestCase):
    def test_fresh_when_matches_expected(self):
        from app.store import Database

        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "f.db")
            import pandas as pd

            # Seed EOD for 2026-10-23
            db.upsert_eod_data(
                pd.DataFrame(
                    [
                        {
                            "symbol": "RELIANCE",
                            "trade_date": "2026-10-23",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "volume": 1,
                            "turnover": 1,
                            "prev_close": 1,
                        }
                    ]
                )
            )
            # Monday noon 26 Oct → expected Fri 23 → age 0 → FRESH
            now = datetime(2026, 10, 26, 12, 0, tzinfo=IST)
            fr = db.freshness(3, now=now)
            self.assertEqual(fr["status"], "FRESH")
            self.assertEqual(fr["age_days"], 0)
            self.assertEqual(fr["age_unit"], "trading_days")
            self.assertEqual(fr["expected_as_of"], "2026-10-23")

    def test_stale_across_holiday_gap(self):
        from app.store import Database
        import pandas as pd

        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "s.db")
            # Latest far behind
            db.upsert_eod_data(
                pd.DataFrame(
                    [
                        {
                            "symbol": "TCS",
                            "trade_date": "2026-09-01",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "volume": 1,
                            "turnover": 1,
                            "prev_close": 1,
                        }
                    ]
                )
            )
            now = datetime(2026, 10, 26, 19, 0, tzinfo=IST)
            fr = db.freshness(3, now=now)
            self.assertEqual(fr["status"], "STALE")
            self.assertGreater(fr["age_days"], 3)


class SchedulerGateTests(unittest.TestCase):
    def test_no_fire_on_weekend(self):
        from app.ingest_scheduler import should_run_scheduled_ingest

        sat = datetime(2026, 10, 24, 19, 0, tzinfo=IST)
        ok, reason = should_run_scheduled_ingest(sat)
        self.assertFalse(ok)
        self.assertEqual(reason, "not_a_trading_day")

    def test_no_fire_before_time(self):
        from app.ingest_scheduler import should_run_scheduled_ingest

        mon = datetime(2026, 10, 26, 17, 0, tzinfo=IST)
        ok, reason = should_run_scheduled_ingest(mon)
        self.assertFalse(ok)
        self.assertEqual(reason, "before_schedule_time")

    def test_fire_after_time_unless_done(self):
        from app.ingest_scheduler import should_run_scheduled_ingest

        mon = datetime(2026, 10, 26, 19, 0, tzinfo=IST)
        ok, reason = should_run_scheduled_ingest(mon)
        self.assertTrue(ok)
        self.assertIn("fire_for_2026-10-26", reason)
        ok2, reason2 = should_run_scheduled_ingest(
            mon, already_succeeded_for="2026-10-26"
        )
        self.assertFalse(ok2)
        self.assertIn("already_done", reason2)

    def test_no_fire_on_holiday(self):
        from app.ingest_scheduler import should_run_scheduled_ingest

        # Independence Day 2025
        day = datetime(2025, 8, 15, 19, 0, tzinfo=IST)
        ok, reason = should_run_scheduled_ingest(day)
        self.assertFalse(ok)
        self.assertEqual(reason, "not_a_trading_day")


class JournalIdempotencyTests(unittest.TestCase):
    def test_journal_roundtrip_and_skip(self):
        from app.ingest_journal import (
            begin_run,
            finish_run,
            last_successful_for_session,
            recent_runs,
        )
        from app.pipeline import run_incremental_ingest
        from app.store import Database
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "j.db"
            db = Database(dbp)
            from app import config as config_mod

            old = config_mod.config.db_path
            object.__setattr__(config_mod.config, "db_path", dbp)
            try:
                rid = begin_run(trigger="schedule", target_session="2026-10-26", provider="test")
                finish_run(
                    rid,
                    status="ok",
                    provider="nse_bhavcopy",
                    eod_rows=10,
                    freshness={"status": "FRESH", "latest_date": "2026-10-26"},
                    message="ok",
                )
                prior = last_successful_for_session("2026-10-26", db_path=dbp)
                self.assertIsNotNone(prior)
                self.assertEqual(prior["status"], "ok")

                # Schedule path should skip without calling providers
                with patch("app.pipeline._try_nse") as nse:
                    result = run_incremental_ingest(
                        db, force_full=False, trigger="schedule", target_session="2026-10-26"
                    )
                nse.assert_not_called()
                self.assertTrue(result.get("skipped"))
                self.assertEqual(result["status"], "ok")
                self.assertGreaterEqual(len(recent_runs(db_path=dbp)), 1)
            finally:
                object.__setattr__(config_mod.config, "db_path", old)

    def test_partial_failure_recorded(self):
        from app.ingest_journal import begin_run, finish_run, journal_summary

        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "err.db"
            rid = begin_run(trigger="manual", target_session="2026-10-20", db_path=dbp)
            finish_run(
                rid,
                status="error",
                error="provider_429_rate_limit",
                message="rate limited",
                db_path=dbp,
            )
            summ = journal_summary(db_path=dbp)
            self.assertEqual(summ["error_count"], 1)
            self.assertEqual(summ["last_run"]["status"], "error")
            self.assertIn("429", summ["last_run"]["error"] or "")


class ApiTests(unittest.TestCase):
    def test_ingest_status_exposes_calendar_and_version(self):
        from fastapi.testclient import TestClient

        import re

        from app.main import APP_VERSION, app

        # Phase-4 lineage: major 5, minor ≥ 4
        m = re.match(r"^5\.(\d+)\.", APP_VERSION)
        self.assertTrue(m and int(m.group(1)) >= 4, APP_VERSION)
        c = TestClient(app)
        r = c.get("/api/ingest/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("calendar", body)
        self.assertIn("scheduler", body)
        self.assertIn("journal", body)
        self.assertTrue(body["calendar"]["holiday_calendar_applied"])
        h = c.get("/api/health")
        self.assertIn("eod_ingest", h.json())


if __name__ == "__main__":
    unittest.main()
