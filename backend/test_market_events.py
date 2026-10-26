"""Tests for market-events calendar — honesty, TZ, dupes, stale, sources."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import market_events as me
from app.main import APP_VERSION, app
from fastapi.testclient import TestClient

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


def _write(path: Path, obj: dict) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


class TimezoneTests(unittest.TestCase):
    def test_ist_to_utc_conversion(self):
        dt = datetime(2026, 10, 26, 15, 30, tzinfo=IST)
        self.assertEqual(me.to_utc_iso(dt), "2026-10-26T10:00:00Z")
        back = me.to_tz_iso(dt.astimezone(UTC), IST)
        self.assertTrue(back.startswith("2026-10-26T15:30:00"))


class HolidaySourceTests(unittest.TestCase):
    def test_holiday_events_have_source_labels_and_tz(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "holidays.json"
            _write(
                p,
                {
                    "source": "test_nse_snapshot",
                    "as_of": "2026-10-01",
                    "last_updated": "2026-10-01T12:00:00+05:30",
                    "timezone": "Asia/Kolkata",
                    "stale_after_days": 365,
                    "holidays": [
                        {"date": "2026-10-02", "name": "Mahatma Gandhi Jayanti"},
                        {"date": "2026-12-25", "name": "Christmas"},
                    ],
                    "limitation": "test",
                },
            )
            me.clear_caches()
            events, feed = me.load_nse_holiday_events(
                now=datetime(2026, 10, 26, 12, 0, tzinfo=IST),
                path=p,
            )
            self.assertEqual(feed["feed"]["status"], "fresh")
            self.assertTrue(feed["feed"]["is_current"])
            self.assertTrue(feed["feed"]["presented_as_current"])
            self.assertEqual(len(events), 2)
            ev = events[0]
            self.assertEqual(ev["source"]["id"], "nse_holidays_snapshot")
            self.assertIn("NSE", ev["source"]["label"])
            self.assertEqual(ev["timezone"], "Asia/Kolkata")
            self.assertTrue(ev["event_time_utc"].endswith("Z") or "+00:00" in ev["event_time_utc"])
            self.assertEqual(ev["content_kind"], "scheduled_fact")
            self.assertTrue(ev["presented_as_current"])
            self.assertIsNone(ev["model_commentary"])
            self.assertFalse(ev["invented"])


class StaleUnavailableTests(unittest.TestCase):
    def test_stale_holiday_feed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "holidays.json"
            _write(
                p,
                {
                    "source": "old",
                    "as_of": "2025-01-01",
                    "last_updated": "2025-01-01T00:00:00+05:30",
                    "timezone": "Asia/Kolkata",
                    "stale_after_days": 30,
                    "holidays": [{"date": "2026-01-26", "name": "Republic Day"}],
                    "limitation": "old snapshot",
                },
            )
            me.clear_caches()
            events, feed = me.load_nse_holiday_events(
                now=datetime(2026, 10, 26, tzinfo=IST),
                path=p,
            )
            self.assertTrue(feed["feed"]["stale"])
            self.assertEqual(feed["feed"]["status"], "stale")
            self.assertFalse(feed["feed"]["is_current"])
            self.assertFalse(feed["feed"]["presented_as_current"])
            self.assertEqual(events[0]["feed_status"], "stale")
            self.assertFalse(events[0]["presented_as_current"])
            self.assertFalse(events[0]["is_current"])
            self.assertIn("not a current", feed["feed"]["reason"].lower())

    def test_missing_operator_file_unavailable(self):
        missing = Path("/tmp/definitely-missing-market-events-xyz.json")
        events, feed = me.load_operator_events(
            now=datetime(2026, 10, 26, tzinfo=IST),
            path=missing,
        )
        self.assertEqual(events, [])
        self.assertEqual(feed["feed"]["status"], "unavailable")
        self.assertIn("Not inventing", feed["feed"]["reason"])

    def test_fo_unavailable_without_cache(self):
        events, feed = me.load_fo_expiry_events(
            now=datetime(2026, 10, 26, tzinfo=IST),
        )
        # Without a live Kotak cache in unit tests, expect unavailable (no invented dates)
        if not events:
            self.assertEqual(feed["feed"]["status"], "unavailable")
            self.assertIn("Not inventing", feed["feed"]["reason"])


class DuplicateChangedTests(unittest.TestCase):
    def test_duplicate_ids_in_operator_feed_kept_once(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.json"
            _write(
                p,
                {
                    "source_id": "op",
                    "source_label": "Op",
                    "as_of": "2026-10-26",
                    "last_updated": "2026-10-26T10:00:00+05:30",
                    "stale_after_days": 60,
                    "timezone": "Asia/Kolkata",
                    "license": "test",
                    "events": [
                        {
                            "id": "same",
                            "title": "Event A",
                            "event_time": "2026-11-01T10:00:00+05:30",
                            "content_kind": "scheduled_fact",
                            "status": "scheduled",
                        },
                        {
                            "id": "same",
                            "title": "Event A dup",
                            "event_time": "2026-11-01T10:00:00+05:30",
                            "content_kind": "scheduled_fact",
                            "status": "scheduled",
                        },
                    ],
                },
            )
            events, _ = me.load_operator_events(
                now=datetime(2026, 10, 26, tzinfo=IST), path=p
            )
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["title"], "Event A")

    def test_changed_event_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.json"
            _write(
                p,
                {
                    "source_id": "op",
                    "source_label": "Op",
                    "as_of": "2026-10-26",
                    "last_updated": "2026-10-26T10:00:00+05:30",
                    "stale_after_days": 60,
                    "timezone": "Asia/Kolkata",
                    "license": "test",
                    "events": [
                        {
                            "id": "mpc1",
                            "title": "MPC decision (revised time)",
                            "event_time": "2026-12-05T10:00:00+05:30",
                            "content_kind": "scheduled_fact",
                            "status": "scheduled",
                            "source_url": "https://www.rbi.org.in/",
                        }
                    ],
                },
            )
            prior = [
                {
                    "id": "mpc1",
                    "title": "MPC decision",
                    "event_time_utc": "2026-12-05T03:00:00Z",
                    "status": "scheduled",
                }
            ]
            events, _ = me.load_operator_events(
                now=datetime(2026, 10, 26, tzinfo=IST),
                path=p,
                prior_by_id={p["id"]: p for p in prior},
            )
            self.assertEqual(len(events), 1)
            self.assertTrue(events[0]["changed"])
            self.assertEqual(events[0]["previous"]["title"], "MPC decision")

    def test_merge_marks_changed_on_conflict(self):
        a = [
            {
                "id": "x",
                "title": "Old",
                "event_time_utc": "2026-01-01T00:00:00Z",
                "status": "scheduled",
            }
        ]
        b = [
            {
                "id": "x",
                "title": "New",
                "event_time_utc": "2026-01-02T00:00:00Z",
                "status": "scheduled",
                "changed": False,
                "previous": None,
            }
        ]
        merged = me.merge_events([a, b])
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["changed"])
        self.assertEqual(merged[0]["title"], "New")


class HonestyTests(unittest.TestCase):
    def test_skips_model_commentary_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.json"
            _write(
                p,
                {
                    "source_id": "op",
                    "as_of": "2026-10-26",
                    "last_updated": "2026-10-26T10:00:00+05:30",
                    "stale_after_days": 60,
                    "events": [
                        {
                            "id": "c1",
                            "title": "AI says Nifty up",
                            "event_time": "2026-10-27T09:00:00+05:30",
                            "content_kind": "model_commentary",
                            "status": "scheduled",
                        },
                        {
                            "id": "f1",
                            "title": "Verified fact",
                            "event_time": "2026-10-28T09:00:00+05:30",
                            "content_kind": "scheduled_fact",
                            "status": "scheduled",
                        },
                    ],
                },
            )
            events, _ = me.load_operator_events(
                now=datetime(2026, 10, 26, tzinfo=IST), path=p
            )
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], "f1")

    def test_incomplete_rows_not_invented(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.json"
            _write(
                p,
                {
                    "source_id": "op",
                    "as_of": "2026-10-26",
                    "last_updated": "2026-10-26T10:00:00+05:30",
                    "stale_after_days": 60,
                    "events": [
                        {"id": "bad", "title": "No time"},
                        {
                            "id": "ok",
                            "title": "Has time",
                            "event_time": "2026-11-01T12:00:00+05:30",
                            "content_kind": "scheduled_fact",
                        },
                    ],
                },
            )
            events, _ = me.load_operator_events(
                now=datetime(2026, 10, 26, tzinfo=IST), path=p
            )
            self.assertEqual([e["id"] for e in events], ["ok"])

    def test_build_calendar_licensing_and_honesty(self):
        with tempfile.TemporaryDirectory() as td:
            hol = Path(td) / "h.json"
            ev = Path(td) / "e.json"
            _write(
                hol,
                {
                    "source": "t",
                    "as_of": "2026-10-01",
                    "last_updated": "2026-10-01T00:00:00+05:30",
                    "stale_after_days": 365,
                    "timezone": "Asia/Kolkata",
                    "holidays": [{"date": "2026-12-25", "name": "Christmas"}],
                },
            )
            _write(
                ev,
                {
                    "source_id": "op",
                    "source_label": "Op",
                    "license": "test-license",
                    "as_of": "2026-10-26",
                    "last_updated": "2026-10-26T10:00:00+05:30",
                    "stale_after_days": 60,
                    "events": [],
                },
            )
            me.clear_caches()
            cal = me.build_calendar(
                now=datetime(2026, 10, 26, tzinfo=IST),
                holidays_path=hol,
                events_path=ev,
                include_fo=False,
            )
            self.assertFalse(cal["honesty"]["invents_dates"])
            self.assertIn("licensing", cal)
            self.assertTrue(cal["count"] >= 1)
            for e in cal["events"]:
                self.assertIn("source", e)
                self.assertIn("event_time_utc", e)
                self.assertIn("timezone", e)
                self.assertIn("feed_status", e)
                self.assertIn("content_kind", e)


class RealHolidayFileTests(unittest.TestCase):
    """Controllable clock against the committed operator snapshot — do not bump as_of here."""

    def test_committed_snapshot_as_of_unchanged_and_stale_vs_frozen_clock(self):
        from app.nse_calendar import holidays_file_path

        path = holidays_file_path()
        self.assertTrue(path.is_file(), path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Operator-verified updates only — this audit must not invent a new as_of
        self.assertEqual(raw.get("as_of"), "2026-01-15")
        self.assertEqual(int(raw.get("stale_after_days") or 120), 120)

        me.clear_caches()
        frozen = datetime(2026, 10, 26, 12, 0, tzinfo=IST)
        events, feed = me.load_nse_holiday_events(now=frozen, path=path)
        self.assertEqual(feed["feed"]["status"], "stale")
        self.assertTrue(feed["feed"]["stale"])
        self.assertFalse(feed["feed"]["is_current"])
        self.assertFalse(feed["feed"]["presented_as_current"])
        self.assertEqual(feed["feed"]["as_of"], "2026-01-15")
        self.assertGreater(float(feed["feed"]["age_days"] or 0), 120)
        self.assertIn("not a current", feed["feed"]["reason"].lower())
        self.assertGreater(len(events), 0)
        for ev in events:
            self.assertEqual(ev["feed_status"], "stale")
            self.assertFalse(ev["presented_as_current"])
            self.assertFalse(ev["is_current"])

        cal = me.build_calendar(
            now=frozen,
            holidays_path=path,
            include_fo=False,
        )
        self.assertTrue(cal["feeds_summary"]["any_stale"])
        self.assertTrue(cal["feeds_summary"]["stale_not_current"])
        nse_feed = next(
            f for f in cal["feeds"] if f.get("source_id") == "nse_holidays_snapshot"
        )
        self.assertEqual(nse_feed["feed"]["status"], "stale")
        self.assertFalse(nse_feed["feed"]["is_current"])
        self.assertFalse(nse_feed["feed"]["presented_as_current"])
        # Holiday rows from the stale snapshot must not claim currency
        nse_ev = [
            e
            for e in cal["events"]
            if (e.get("source") or {}).get("id") == "nse_holidays_snapshot"
        ]
        self.assertGreater(len(nse_ev), 0)
        for ev in nse_ev:
            self.assertFalse(ev["presented_as_current"])


class ApiUiConsistencyTests(unittest.TestCase):
    def test_version_and_api_shape(self):
        self.assertTrue(
            "market-events" in APP_VERSION
            or "strategy-eval" in APP_VERSION
            or "holiday-freshness" in APP_VERSION
            or APP_VERSION.startswith("5.11")
            or APP_VERSION.startswith("5.12"),
            APP_VERSION,
        )
        c = TestClient(app)
        meta = c.get("/api/market-events/meta")
        self.assertEqual(meta.status_code, 200)
        self.assertFalse(meta.json()["honesty"]["invents_dates"])
        self.assertIn("scheduled_fact", meta.json()["content_kinds"])

        r = c.get("/api/market-events", params={"include_fo": "false"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("disclaimer", body)
        self.assertIn("feeds", body)
        self.assertIn("events", body)
        self.assertIn("licensing", body)
        self.assertEqual(body.get("honesty", {}).get("invents_forecasts"), False)
        self.assertIn("stale_not_current", body.get("feeds_summary") or {})
        # UI contract fields on each event
        for ev in body["events"]:
            for key in (
                "id",
                "title",
                "source",
                "event_time_utc",
                "event_time_local",
                "timezone",
                "status",
                "feed_status",
                "content_kind",
                "model_commentary",
                "presented_as_current",
                "is_current",
            ):
                self.assertIn(key, ev, key)
            self.assertIsNone(ev["model_commentary"])
            self.assertIn("label", ev["source"])
            self.assertIn("license", ev["source"])
            if ev["feed_status"] != "fresh":
                self.assertFalse(ev["presented_as_current"])
                self.assertFalse(ev["is_current"])

        root = c.get("/").json()
        self.assertIn("market_events", root)


if __name__ == "__main__":
    unittest.main()
