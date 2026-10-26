"""Manual trade journal + capital accounting tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ.setdefault("BIND_HOST", "127.0.0.1")
os.environ.setdefault("EOD_INGEST_SCHEDULE_ENABLED", "false")
os.environ["API_KEY"] = ""  # mutations open in unit tests

from app import trade_ledger as ledger  # noqa: E402


class LedgerCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.db"
        ledger.ensure_schema(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_capital_deposits_withdrawals_and_book(self):
        ledger.add_capital_movement(
            kind="starting_capital", amount=100_000, path=self.path
        )
        ledger.add_capital_movement(kind="deposit", amount=10_000, path=self.path)
        ledger.add_capital_movement(kind="withdrawal", amount=5_000, path=self.path)
        s = ledger.capital_summary(path=self.path)
        self.assertEqual(s["capital"]["starting_capital"], 100_000)
        self.assertEqual(s["capital"]["deposits"], 10_000)
        self.assertEqual(s["capital"]["withdrawals"], 5_000)
        self.assertEqual(s["capital"]["book_equity"], 105_000)
        self.assertIn("user_entered", s["source_label"])

    def test_partial_exit_pnl_and_fees(self):
        ledger.add_capital_movement(
            kind="starting_capital", amount=50_000, path=self.path
        )
        t = ledger.open_trade(
            instrument="RELIANCE",
            direction="LONG",
            quantity=10,
            entry_price=100,
            fees=20,
            path=self.path,
        )
        # Partial exit 4 @ 110, fees 5 → gross 40, net vs fees later
        out = ledger.record_exit(
            t["id"], quantity=4, price=110, fees=5, path=self.path
        )
        self.assertEqual(out["trade"]["status"], "open")
        self.assertAlmostEqual(out["trade"]["quantity"], 6)
        self.assertAlmostEqual(out["exit"]["realized_pnl"], 35.0)  # 40-5

        trades = ledger.list_trades(path=self.path)
        self.assertEqual(len(trades), 1)
        # realized on trade = gross 40 - fees_total (20+5) = 15
        self.assertAlmostEqual(trades[0]["realized_gross"], 40.0)
        self.assertAlmostEqual(trades[0]["realized_pnl"], 15.0)
        self.assertAlmostEqual(trades[0]["fees_total"], 25.0)

        # Close rest @ 90 → gross (90-100)*6 = -60
        ledger.record_exit(t["id"], quantity=6, price=90, fees=5, path=self.path)
        trades = ledger.list_trades(path=self.path)
        self.assertEqual(trades[0]["status"], "closed")
        # gross 40-60=-20; fees 20+5+5=30; realized=-50
        self.assertAlmostEqual(trades[0]["realized_gross"], -20.0)
        self.assertAlmostEqual(trades[0]["realized_pnl"], -50.0)
        s = ledger.capital_summary(path=self.path)
        self.assertAlmostEqual(s["capital"]["realized_pnl"], -50.0)
        self.assertAlmostEqual(s["capital"]["costs_fees_total"], 30.0)
        self.assertAlmostEqual(s["capital"]["book_equity"], 49_950.0)

    def test_short_realized(self):
        t = ledger.open_trade(
            instrument="TCS",
            direction="SHORT",
            quantity=2,
            entry_price=200,
            fees=0,
            path=self.path,
        )
        ledger.record_exit(t["id"], quantity=2, price=180, fees=0, path=self.path)
        trades = ledger.list_trades(path=self.path)
        self.assertAlmostEqual(trades[0]["realized_pnl"], 40.0)

    def test_correction_retains_audit(self):
        m = ledger.add_capital_movement(
            kind="deposit", amount=1000, path=self.path, notes="a"
        )
        ledger.correct_capital_movement(
            m["id"], amount=1500, reason="typo fix", path=self.path
        )
        active = ledger.list_capital_movements(path=self.path)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["amount"], 1500)
        all_m = ledger.list_capital_movements(include_inactive=True, path=self.path)
        self.assertEqual(len(all_m), 2)
        audit = ledger.list_audit(path=self.path)
        self.assertTrue(any(a["action"] == "correct" for a in audit))
        self.assertTrue(any(a.get("reason") == "typo fix" for a in audit))

    def test_trade_correct_requires_reason(self):
        t = ledger.open_trade(
            instrument="INFY",
            direction="LONG",
            quantity=1,
            entry_price=10,
            path=self.path,
        )
        with self.assertRaises(ValueError):
            ledger.correct_trade(t["id"], reason="", path=self.path)
        ledger.correct_trade(
            t["id"], reason="fix note", notes="updated", path=self.path
        )
        trades = ledger.list_trades(path=self.path)
        self.assertEqual(trades[0]["notes"], "updated")

    def test_unrealized_missing_quote(self):
        t = ledger.open_trade(
            instrument="NOSYMBOLZZ",
            direction="LONG",
            quantity=1,
            entry_price=100,
            path=self.path,
        )
        with patch("app.trade_ledger._reliable_quote") as rq:
            rq.return_value = {
                "available": False,
                "reason": "no_ltp",
                "reliability": "unavailable",
            }
            u = ledger.unrealized_for_trade(t)
        self.assertFalse(u["available"])
        self.assertIsNone(u["estimated_unrealized_pnl"])
        s = ledger.capital_summary(path=self.path)
        # Force open trade path with mock
        with patch("app.trade_ledger.unrealized_for_trade", return_value=u):
            with patch("app.trade_ledger.list_trades", return_value=[{**t, "realized_pnl": -0.0, "fees_total": 0, "exits": []}]):
                with patch(
                    "app.trade_ledger.list_capital_movements",
                    return_value=[
                        {"kind": "starting_capital", "amount": 10000},
                    ],
                ):
                    # call internals carefully — use real summary with patched quote
                    pass
        with patch("app.trade_ledger._reliable_quote") as rq:
            rq.return_value = {
                "available": False,
                "reason": "no_ltp",
                "reliability": "unavailable",
            }
            s = ledger.capital_summary(path=self.path)
        self.assertFalse(s["estimated_unrealized"]["available"])
        self.assertIsNone(s["estimated_unrealized"]["total"])
        # book equity unchanged by missing unrealized
        self.assertIn("book_equity", s["capital"])

    def test_unrealized_when_quote_available(self):
        t = ledger.open_trade(
            instrument="RELIANCE",
            direction="LONG",
            quantity=2,
            entry_price=100,
            fees=0,
            path=self.path,
        )
        with patch("app.trade_ledger._reliable_quote") as rq:
            rq.return_value = {
                "available": True,
                "ltp": 110.0,
                "source": "kotak_neo_ws",
                "age_sec": 1.0,
                "reliability": "live_quote",
                "label": "estimated_unrealized_live_quote",
            }
            u = ledger.unrealized_for_trade(
                {**t, "status": "open", "quantity": 2, "entry_price": 100, "direction": "LONG"}
            )
            s = ledger.capital_summary(path=self.path)
        self.assertTrue(u["available"])
        self.assertAlmostEqual(u["estimated_unrealized_pnl"], 20.0)
        self.assertEqual(u["label"], "estimated_unrealized_live_quote")
        self.assertTrue(s["estimated_unrealized"]["available"])
        self.assertAlmostEqual(s["estimated_unrealized"]["total"], 20.0)
        # Separately labeled — not silently in book
        self.assertNotEqual(
            s["capital"]["book_equity"], s["estimated_equity_mark"]["value"]
        )

    def test_persistence_reload(self):
        ledger.add_capital_movement(
            kind="starting_capital", amount=1_000, path=self.path
        )
        t = ledger.open_trade(
            instrument="SBIN",
            direction="LONG",
            quantity=5,
            entry_price=50,
            path=self.path,
        )
        # New connection / reload
        trades = ledger.list_trades(path=self.path)
        self.assertEqual(trades[0]["id"], t["id"])
        self.assertEqual(len(ledger.list_capital_movements(path=self.path)), 1)

    def test_exit_qty_over_remaining_rejected(self):
        t = ledger.open_trade(
            instrument="HDFC",
            direction="LONG",
            quantity=1,
            entry_price=10,
            path=self.path,
        )
        with self.assertRaises(ValueError):
            ledger.record_exit(t["id"], quantity=2, price=11, path=self.path)


class ApiPrivacyTests(unittest.TestCase):
    def test_health_omits_trade_rows(self):
        from fastapi.testclient import TestClient

        from app.main import APP_VERSION, app
        from app.version_assert import minor_at_least

        self.assertTrue(minor_at_least(APP_VERSION, 9), APP_VERSION)
        c = TestClient(app)
        h = c.get("/api/health").json()
        blob = str(h)
        self.assertNotIn("open_positions", blob)
        self.assertNotIn("realized_pnl", blob)
        self.assertIn("ledger_note", h)
        root = c.get("/").json()
        self.assertIn("ledger", root)
        # summary works
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.db"
            with patch("app.trade_ledger._db_path", return_value=path):
                with patch("app.routers.trade_ledger.ledger._db_path", return_value=path):
                    # Use default path from config for API — just ensure endpoint exists
                    r = c.get("/api/ledger/summary")
        self.assertEqual(r.status_code, 200)
        self.assertIn("disclaimer", r.json())
        self.assertIn("user-entered", r.json()["disclaimer"].lower())

    def test_api_key_gates_ledger_post(self):
        from fastapi.testclient import TestClient

        from app import config as cfg
        from app.main import app

        old = cfg.config.api_key
        try:
            object.__setattr__(cfg.config, "api_key", "test-ledger-key")
            c = TestClient(app)
            r = c.post(
                "/api/ledger/trades",
                json={
                    "instrument": "X",
                    "direction": "LONG",
                    "quantity": 1,
                    "entry_price": 1,
                },
            )
            self.assertEqual(r.status_code, 401)
            r2 = c.post(
                "/api/ledger/trades",
                headers={"X-API-Key": "test-ledger-key"},
                json={
                    "instrument": "X",
                    "direction": "LONG",
                    "quantity": 1,
                    "entry_price": 1,
                },
            )
            self.assertEqual(r2.status_code, 200)
        finally:
            object.__setattr__(cfg.config, "api_key", old)


if __name__ == "__main__":
    unittest.main()
