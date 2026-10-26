"""
Kotak adapter / protocol contract tests — offline fixtures only.

Does NOT claim live WebSocket or credentialed end-to-end verification.
No network calls; no real consumer keys or TOTP in fixtures.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.kotak.protocol import (  # noqa: E402
    HEADER_SIZE,
    MSG_INDEX,
    MSG_MARKET_PICTURE,
    IndexTick,
    MiniTouch,
    decode_packet,
    split_batch,
)
from app.market_types import LiveQuote  # noqa: E402
from app.version_assert import minor_at_least  # noqa: E402
from app.main import APP_VERSION  # noqa: E402

_HEADER = struct.Struct("<HHbBBBB")
_INDEX_BODY = struct.Struct("<IiiiiiQiiidBi21s")
_MINI_BODY = struct.Struct("<IqIqIiiIBI")
NSE_CM = 1
DIVIDERS = {NSE_CM: 100}


def _header(message_length, message_code, exchange_id=NSE_CM, level=0):
    return _HEADER.pack(message_length, message_code, exchange_id, level, 0, 0, 0)


def _mini_packet():
    body = _MINI_BODY.pack(
        11536, 1234567890, 150050, 10, 149900, 123, 150, 1, 2, 1
    )
    length = HEADER_SIZE + len(body)
    return _header(length, MSG_MARKET_PICTURE, level=1) + body


def _index_packet():
    body = _INDEX_BODY.pack(
        26000,
        2000000,
        1990000,
        2010000,
        1980000,
        2005000,
        1234567890,
        2100000,
        1500000,
        150,
        0.0,
        2,
        100,
        b"NIFTY 50",
    )
    length = HEADER_SIZE + len(body)
    return _header(length, MSG_INDEX, level=0) + body


class ProtocolContractTests(unittest.TestCase):
    def test_split_and_decode_index_offline(self):
        pkt = _index_packet()
        parts = split_batch(pkt)
        self.assertEqual(len(parts), 1)
        msg = decode_packet(parts[0], DIVIDERS)
        self.assertIsInstance(msg, IndexTick)
        self.assertEqual(str(msg.instrument_token), "26000")
        # Prices use divider 100
        # Fixture packs last price as 2005000 raw / divider 100
        self.assertAlmostEqual(msg.last_traded_price, 20050.0, places=2)
        self.assertGreater(msg.last_traded_price, 0)

    def test_decode_mini_touch_offline(self):
        msg = decode_packet(_mini_packet(), DIVIDERS)
        self.assertIsInstance(msg, MiniTouch)
        tok = getattr(msg, "instrument_token", None) or getattr(msg, "token", None)
        self.assertEqual(str(tok), "11536")
        ltp = getattr(msg, "last_traded_price", None)
        if ltp is None:
            ltp = getattr(msg, "ltp", None)
        self.assertAlmostEqual(float(ltp), 1500.50, places=2)

    def test_batch_of_two_packets(self):
        batch = _index_packet() + _mini_packet()
        parts = split_batch(batch)
        self.assertEqual(len(parts), 2)
        self.assertIsInstance(decode_packet(parts[0], DIVIDERS), IndexTick)
        self.assertIsInstance(decode_packet(parts[1], DIVIDERS), MiniTouch)


class LiveVsFallbackHonestyTests(unittest.TestCase):
    def test_yahoo_source_is_fallback_not_broker_live(self):
        q = LiveQuote(
            symbol="RELIANCE",
            ltp=100.0,
            quote_ts_unix=1_700_000_000.0,
            fetched_at_unix=1_700_000_001.0,
            age_sec=1.0,
            feed_status="ok",
            source="yahoo_chart",
            price_kind="intraday_bar_close",
            market_data_state="FALLBACK",
            provider_class="yahoo",
            is_current_live=False,
        )
        d = q.to_dict() if hasattr(q, "to_dict") else q.__dict__
        state = d.get("market_data_state") or d.get("provenance")
        self.assertEqual(str(state).upper() if isinstance(state, str) else state, "FALLBACK")
        self.assertFalse(d.get("is_current_live"))
        src = str(d.get("source") or "")
        self.assertIn("yahoo", src.lower())
        self.assertNotEqual(src.lower(), "kotak_ws")

    def test_kotak_live_flags_when_ws_quote(self):
        q = LiveQuote(
            symbol="RELIANCE",
            ltp=101.0,
            quote_ts_unix=1_700_000_000.0,
            fetched_at_unix=1_700_000_000.5,
            age_sec=0.5,
            feed_status="ok",
            source="kotak_ws",
            price_kind="ltp",
            market_data_state="LIVE",
            provider_class="kotak",
            is_current_live=True,
        )
        d = q.to_dict() if hasattr(q, "to_dict") else q.__dict__
        self.assertEqual(d.get("market_data_state"), "LIVE")
        self.assertTrue(d.get("is_current_live"))


class SessionWithoutCredentialsTests(unittest.TestCase):
    def test_session_without_key_is_not_authenticated(self):
        """Contract: empty consumer key must not invent a connected session."""
        from app.kotak.session import KotakSession

        with patch("app.kotak.session.consumer_key", return_value=None):
            sess = KotakSession()
            status = sess.status() if hasattr(sess, "status") else {}
            if isinstance(status, dict):
                self.assertFalse(
                    status.get("authenticated")
                    or status.get("connected")
                    or status.get("logged_in")
                )
            # No access token fabricated
            token = getattr(sess, "access_token", None) or getattr(sess, "sid", None)
            self.assertFalse(bool(token))


class VersionFloorTests(unittest.TestCase):
    def test_app_version_floor(self):
        self.assertTrue(minor_at_least(APP_VERSION, 12), APP_VERSION)


if __name__ == "__main__":
    unittest.main()
