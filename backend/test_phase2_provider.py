"""Phase 2 — provider boundary, tick guard, fallback labeling (offline / deterministic)."""
from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ["LIVE_QUOTE_STALE_SEC"] = "5"
os.environ["ALLOW_YAHOO_LTP_FALLBACK"] = "true"
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")

from app.kotak.protocol import decode_packet, split_batch  # noqa: E402
from app.kotak.tick_guard import (  # noqa: E402
    public_ws_status,
    sanitize_error_text,
    should_accept_tick,
)
from app.market_session import annotate_live_quote, session_snapshot  # noqa: E402
from app.market_types import LiveQuote  # noqa: E402
from app.providers.live_quote_provider import (  # noqa: E402
    provider_policy_public,
    resolve_live_quote,
    yahoo_fallback_allowed,
)

IST = ZoneInfo("Asia/Kolkata")


class TickGuardTests(unittest.TestCase):
    def test_reject_out_of_order(self):
        ok, reason = should_accept_tick(
            incoming_ts=100.0, previous_ts=200.0, incoming_ltp=10.0
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "out_of_order")

    def test_accept_newer(self):
        ok, reason = should_accept_tick(
            incoming_ts=201.0, previous_ts=200.0, incoming_ltp=10.0
        )
        self.assertTrue(ok)

    def test_reject_bad_ltp(self):
        ok, reason = should_accept_tick(
            incoming_ts=1.0, previous_ts=None, incoming_ltp=None
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_ltp")
        ok2, _ = should_accept_tick(incoming_ts=1.0, previous_ts=None, incoming_ltp=-1)
        self.assertFalse(ok2)

    def test_sanitize_redacts_secrets(self):
        raw = "auth failed auth=daca59eb-caeb-4f9a-ac44-31d427e65b00 sid=abc"
        clean = sanitize_error_text(raw)
        self.assertNotIn("daca59eb", clean)
        self.assertIn("REDACTED", clean)

    def test_public_ws_status_strips_query(self):
        st = public_ws_status(
            {
                "connected": True,
                "feed_url": "wss://sfeed.example/apifeed?token=sekrit",
                "last_error": "auth=sekrit-value-here",
            }
        )
        self.assertNotIn("token=", st["feed_url"])
        self.assertNotIn("sekrit-value", st["last_error"] or "")


class MalformedPacketTests(unittest.TestCase):
    def test_garbage_batch_yields_no_crash(self):
        # split_batch / decode should tolerate junk
        junk = b"\x00\x01\x02\xffnotapacket"
        packets = list(split_batch(junk))
        for p in packets:
            try:
                decode_packet(p, {1: 100})
            except Exception:
                pass  # expected for malformed


class ProviderBoundaryTests(unittest.TestCase):
    def test_yahoo_fallback_policy_default(self):
        self.assertTrue(yahoo_fallback_allowed())

    def test_provider_policy_public_honest(self):
        pol = provider_policy_public()
        self.assertEqual(pol["broker"], "kotak_neo_ws")
        self.assertIn("native_batch", pol["broker_protocol"])
        self.assertFalse(pol["claims"]["verified_live_e2e_this_build"])
        self.assertFalse(pol["demo_allowed"])

    def test_resolve_uses_kotak_when_present(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        kq = annotate_live_quote(
            LiveQuote(
                symbol="RELIANCE",
                ltp=1400.0,
                quote_ts_unix=now - 1,
                fetched_at_unix=now,
                age_sec=1.0,
                feed_status="LIVE",
                source="kotak_neo_ws",
            ),
            now_unix=now,
            session=sess,
        )

        with patch(
            "app.providers.live_quote_provider._kotak_quote", return_value=kq
        ), patch(
            "app.providers.live_quote_provider._kotak_connected", return_value=True
        ):
            res = resolve_live_quote("RELIANCE.NS")
        self.assertEqual(res.path, "kotak_neo_ws")
        self.assertTrue(res.quote.is_current_live)
        self.assertEqual(res.quote.to_dict()["provenance"], "live")

    def test_resolve_yahoo_fallback_labeled(self):
        at = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
        sess = session_snapshot(at)
        now = at.timestamp()
        yq = annotate_live_quote(
            LiveQuote(
                symbol="RELIANCE",
                ltp=1400.0,
                quote_ts_unix=now - 1,
                fetched_at_unix=now,
                age_sec=1.0,
                feed_status="LIVE",
                source="yahoo_chart",
            ),
            now_unix=now,
            session=sess,
        )
        with patch(
            "app.providers.live_quote_provider._kotak_quote", return_value=None
        ), patch(
            "app.providers.live_quote_provider._kotak_connected", return_value=False
        ), patch(
            "app.providers.live_quote_provider.yahoo_fallback_allowed",
            return_value=True,
        ), patch(
            "app.providers.live_quote_provider._yahoo_quote", return_value=yq
        ):
            res = resolve_live_quote("RELIANCE.NS")
        self.assertEqual(res.path, "yahoo_chart_fallback")
        self.assertEqual(res.quote.market_data_state, "FALLBACK")
        self.assertFalse(res.quote.is_current_live)
        self.assertEqual(res.quote.to_dict()["provenance"], "fallback")

    def test_resolve_fail_closed_when_fallback_disabled(self):
        with patch(
            "app.providers.live_quote_provider._kotak_quote", return_value=None
        ), patch(
            "app.providers.live_quote_provider._kotak_connected", return_value=False
        ), patch(
            "app.providers.live_quote_provider.yahoo_fallback_allowed",
            return_value=False,
        ):
            res = resolve_live_quote("RELIANCE.NS")
        self.assertEqual(res.path, "unavailable")
        self.assertIsNone(res.quote.ltp)
        self.assertIn(res.quote.market_data_state, ("ERROR", "UNAVAILABLE", "PRE_MARKET", "POST_MARKET", "WEEKEND"))


class HubCommitTests(unittest.TestCase):
    def test_out_of_order_dropped_and_counted(self):
        from app.kotak.feed_hub import FeedHub

        hub = FeedHub()
        now = datetime(2026, 10, 26, 11, 0, tzinfo=IST).timestamp()
        q1 = LiveQuote(
            symbol="TCS",
            ltp=3500.0,
            quote_ts_unix=now,
            fetched_at_unix=now,
            age_sec=0.0,
            feed_status="LIVE",
            source="kotak_neo_ws",
        )
        q_old = LiveQuote(
            symbol="TCS",
            ltp=3499.0,
            quote_ts_unix=now - 5,
            fetched_at_unix=now,
            age_sec=5.0,
            feed_status="LIVE",
            source="kotak_neo_ws",
        )
        self.assertTrue(hub._commit_quote("nse_cm|11536", q1))
        self.assertFalse(hub._commit_quote("nse_cm|11536", q_old))
        self.assertEqual(hub._ticks_dropped_ooo, 1)
        cached = hub.get_quote("nse_cm|11536")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.ltp, 3500.0)

    def test_ws_client_fatal_auth_in_status(self):
        from app.kotak.session import SessionCredentials
        from app.kotak.ws_client import KotakWebSocketClient

        creds = SessionCredentials(
            ucc="TESTUCC",
            sid="test-sid-value",
            auth="test-auth-value",
            feed_url="wss://example.invalid/apifeed",
        )
        client = KotakWebSocketClient(creds)
        client._fatal_auth = True
        client._last_error = "auth=sekrit-token-value"
        st = client.status()
        self.assertTrue(st["fatal_auth"])
        self.assertNotIn("sekrit", st["last_error"] or "")
        self.assertEqual(st["protocol"], "native_batch_apifeed_hs")


class FeedStatusApiTests(unittest.TestCase):
    def test_feed_status_no_secrets(self):
        from fastapi.testclient import TestClient

        import re

        from app.main import APP_VERSION, app

        # Phase-2 lineage: major 5, minor ≥ 2 (accepts 5.12.0-strategy-eval etc.)
        m = re.match(r"^5\.(\d+)\.", APP_VERSION)
        self.assertTrue(m and int(m.group(1)) >= 2, APP_VERSION)
        c = TestClient(app)
        r = c.get("/api/kotak/feed/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        blob = str(body).lower()
        self.assertNotIn("mpin", blob)
        self.assertIn("provider_policy", body)
        self.assertFalse(body["coverage_claims"]["live_e2e_verified_in_ci"])
        self.assertIn("not_live_e2e", body["coverage_claims"]["ltp"])

    def test_health_exposes_fallback_flag(self):
        from fastapi.testclient import TestClient

        from app.main import app

        c = TestClient(app)
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        lq = r.json()["feeds"]["live_quotes"]
        self.assertIn("yahoo_ltp_fallback_allowed", lq)
        self.assertEqual(lq["broker_protocol"], "native_batch_apifeed_hs")


if __name__ == "__main__":
    unittest.main()
