"""Phase 2 — Kotak scrip master, protocol decode, L2/OBI, bar aggregator (offline)."""
from __future__ import annotations

import os
import struct
import sys
import unittest
from datetime import date
from pathlib import Path

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.kotak.bars import BarAggregator  # noqa: E402
from app.kotak.depth import build_order_book, order_book_imbalance  # noqa: E402
from app.kotak.protocol import (  # noqa: E402
    HEADER_SIZE,
    MSG_INDEX,
    MSG_MARKET_PICTURE,
    DepthLevel,
    MarketPicture,
    decode_packet,
    split_batch,
)
from app.kotak.scrip_master import ScripMaster, _decode_expiry  # noqa: E402
from app.market_types import LiveQuote  # noqa: E402

_HEADER = struct.Struct("<HHbBBBB")
_INDEX_BODY = struct.Struct("<IiiiiiQiiidBi21s")
_MINI_BODY = struct.Struct("<IqIqIiiIBI")
_MP_BODY = struct.Struct("<IqqqqqIIIIIqIIIIhiIdiIIIIIBI")
_DEPTH_ROW = struct.Struct("<qii")
NSE_CM = 1
DIVIDERS = {NSE_CM: 100}


def _header(message_length, message_code, exchange_id=NSE_CM, level=0, auction=0):
    return _HEADER.pack(message_length, message_code, exchange_id, level, auction, 0, 0)


def _mini_packet():
    body = _MINI_BODY.pack(
        11536,
        1234567890,
        150050,
        10,
        149900,
        123,
        150,
        1,
        2,
        1,
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


def _market_picture_packet(level=8, buy_n=5, sell_n=5):
    body = _MP_BODY.pack(
        2885,
        1000,
        2000,
        50000,
        1234567890,
        1234567891,
        150000,
        149000,
        151000,
        148000,
        150050,
        10,
        150025,
        0,
        buy_n,
        sell_n,
        0,
        123,
        500,
        1234567.0,
        105,
        165000,
        135000,
        200000,
        100000,
        1,
        2,
        1,
    )
    fixed = body.ljust(144 - HEADER_SIZE, b"\x00")
    rows = b""
    for i in range(buy_n):
        rows += _DEPTH_ROW.pack(1000 - i * 50, 150000 - i * 5, 5 + i)
    for i in range(sell_n):
        rows += _DEPTH_ROW.pack(800 + i * 40, 150100 + i * 5, 3 + i)
    payload = fixed + rows
    length = HEADER_SIZE + len(payload)
    return _header(length, MSG_MARKET_PICTURE, level=level) + payload


class TestProtocol(unittest.TestCase):
    def test_split_and_decode_mini(self):
        pkt = _mini_packet()
        packets = split_batch(pkt + _index_packet())
        self.assertEqual(len(packets), 2)
        mini = decode_packet(packets[0], DIVIDERS)
        self.assertEqual(mini.type, "scrip_lite")
        self.assertAlmostEqual(mini.last_traded_price, 1500.50)
        self.assertAlmostEqual(mini.close_price, 1499.00)
        idx = decode_packet(packets[1], DIVIDERS)
        self.assertEqual(idx.type, "index")
        self.assertEqual(idx.name, "NIFTY 50")
        self.assertAlmostEqual(idx.last_traded_price, 20050.0)

    def test_decode_5_level_depth(self):
        msg = decode_packet(_market_picture_packet(level=8, buy_n=5, sell_n=5), DIVIDERS)
        self.assertIsInstance(msg, MarketPicture)
        self.assertEqual(len(msg.buy), 5)
        self.assertEqual(len(msg.sell), 5)
        self.assertEqual(msg.open_interest, 500)
        self.assertAlmostEqual(msg.last_traded_price, 1500.50)
        self.assertAlmostEqual(msg.average_trade_price, 1500.25)


class TestDepthOBI(unittest.TestCase):
    def test_obi_and_spread(self):
        bids = [
            DepthLevel(quantity=100, price=100.0, orders=2),
            DepthLevel(quantity=50, price=99.9, orders=1),
        ]
        asks = [
            DepthLevel(quantity=40, price=100.1, orders=1),
            DepthLevel(quantity=60, price=100.2, orders=3),
        ]
        book = build_order_book(bids, asks, max_levels=5)
        self.assertAlmostEqual(book.obi, (150 - 100) / 250)
        self.assertAlmostEqual(book.spread_pct, (0.1 / 100.05) * 100.0, places=6)
        self.assertIsNone(order_book_imbalance(0, 0))

    def test_five_levels_from_packet(self):
        msg = decode_packet(_market_picture_packet(level=8, buy_n=5, sell_n=5), DIVIDERS)
        book = build_order_book(msg.buy, msg.sell, max_levels=5)
        self.assertEqual(len(book.bids), 5)
        self.assertEqual(len(book.asks), 5)
        self.assertIsNotNone(book.obi)
        self.assertIsNotNone(book.spread_pct)


class TestBarAggregator(unittest.TestCase):
    def test_1m_5m_15m_ohlcv_oi(self):
        agg = BarAggregator()
        key = "nse_fo|48704"
        # 10:00:10 IST-ish unix — use fixed epoch buckets
        t0 = 1_700_000_000  # aligns to round seconds
        # Align to exact 15m boundary
        t0 = t0 - (t0 % 900)
        closed = []
        closed += agg.on_tick(key=key, price=100.0, ts_unix=t0 + 5, session_volume=1000, oi=50)
        closed += agg.on_tick(key=key, price=102.0, ts_unix=t0 + 30, session_volume=1100, oi=55)
        closed += agg.on_tick(key=key, price=101.0, ts_unix=t0 + 70, session_volume=1200, oi=60)
        # Crossing into next 1m should close one 1m bar
        self.assertTrue(any(b.interval == "1m" and b.closed for b in closed))
        cur_1m = agg.current_bar(key, "1m")
        self.assertIsNotNone(cur_1m)
        self.assertEqual(cur_1m.open, 101.0)
        bars_5 = agg.bars_with_current(key, "5m")
        self.assertGreaterEqual(len(bars_5), 1)
        bars_15 = agg.bars_with_current(key, "15m")
        self.assertEqual(bars_15[0]["open"], 100.0)
        self.assertEqual(bars_15[0]["high"], 102.0)
        self.assertEqual(bars_15[0]["oi"], 60)


class TestExpiryDecode(unittest.TestCase):
    def test_kotak_fo_expiry_offset(self):
        # NIFTY26OCTFUT sample pExpiryDate
        d = _decode_expiry(1_477_578_600)
        self.assertEqual(d, date(2026, 10, 27))


class TestScripMasterLive(unittest.TestCase):
    """Hits Kotak public lapi — skipped only if network/download fails hard."""

    def test_resolve_equity_and_future_no_hardcoded_tokens(self):
        sm = ScripMaster(cache_dir=ROOT / "data" / "kotak_cache")
        try:
            sm.ensure_loaded()
        except RuntimeError as e:
            self.skipTest(f"scrip master unavailable: {e}")
        rel = sm.resolve_equity("RELIANCE")
        self.assertEqual(rel.exchange_segment, "nse_cm")
        self.assertTrue(rel.instrument_token.isdigit())
        self.assertEqual(rel.kind, "EQ")
        self.assertGreater(rel.tick_size, 0)
        fut = sm.nearest_future("NIFTY")
        self.assertEqual(fut.kind, "FUT")
        self.assertEqual(fut.underlying, "NIFTY")
        self.assertTrue(fut.instrument_token.isdigit())
        self.assertGreater(fut.lot_size, 0)
        self.assertIsNotNone(fut.expiry)
        # Options: pick a near expiry + strike from chain
        exps = sm.list_expiries("NIFTY", kind="OPT")
        self.assertTrue(exps)
        chain = sm.option_chain_tokens("NIFTY", exps[0])
        self.assertTrue(chain)
        ce = next(i for i in chain if i.option_right == "CE" and i.strike)
        resolved = sm.resolve_option("NIFTY", ce.expiry, ce.strike, "CE")
        self.assertEqual(resolved.instrument_token, ce.instrument_token)


class TestLiveQuoteSchema(unittest.TestCase):
    def test_phase2_fields_roundtrip(self):
        q = LiveQuote(
            symbol="RELIANCE",
            ltp=1500.5,
            quote_ts_unix=1234567890.0,
            fetched_at_unix=1234567891.0,
            age_sec=1.0,
            feed_status="LIVE",
            source="kotak_neo_ws",
            oi=500.0,
            prev_day_oi=480.0,
            ltq=10.0,
            atp=1500.25,
            obi=0.2,
            spread_pct=0.01,
            depth_bids=({"price": 1500.0, "quantity": 100, "orders": 2},),
            depth_asks=({"price": 1500.1, "quantity": 80, "orders": 1},),
            instrument_token="2885",
            exchange_segment="nse_cm",
            exchange_timestamp=1234567890,
        )
        d = q.to_dict()
        self.assertEqual(d["oi"], 500.0)
        self.assertEqual(d["prev_day_oi"], 480.0)
        self.assertEqual(len(d["depth_bids"]), 1)
        self.assertEqual(d["price"], 1500.5)


class TestAppImport(unittest.TestCase):
    def test_app_boots_with_kotak_router(self):
        from app.main import APP_VERSION, app

        self.assertTrue(
            APP_VERSION.startswith("4.") or APP_VERSION.startswith("5."),
            APP_VERSION,
        )
        paths = {getattr(r, "path", None) for r in app.routes}
        self.assertIn("/api/kotak/session", paths)
        self.assertIn("/api/kotak/feed/status", paths)
        self.assertIn("/api/kotak/scrip/resolve/equity/{symbol}", paths)


if __name__ == "__main__":
    unittest.main()
