"""Deterministic signal-availability honesty — fixtures + controllable clock; no live markets."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
os.environ["AUTH_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "ci-test-secret-key-32chars-min!!"
os.environ["MARKET_DATA_ADAPTER"] = "live"

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_PATH"] = _tmp.name

from fastapi.testclient import TestClient  # noqa: E402

from app import config as config_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.platform_db import PlatformDB  # noqa: E402
from app.signal_availability import (  # noqa: E402
    DATA_BLOCKED,
    GATE_BLOCKED,
    LEDGER_DEMO_FILTERED,
    LEDGER_EMPTY,
    LEDGER_HAS_ROWS,
    NO_QUALIFYING,
    QUALIFYING,
    annotate_call_display,
    attach_board_availability,
    summarize_board_availability,
    summarize_expectancy_honesty,
    summarize_ledger_availability,
)


class ClassifyBoardTests(unittest.TestCase):
    def test_qualifying_buy(self):
        board = {
            "desk": "swing",
            "status": "ok",
            "data_status": {"status": "FRESH"},
            "calls": [
                {
                    "symbol": "AAA",
                    "side": "BUY",
                    "desk": "swing",
                    "sources": ["weekly_swing"],
                    "as_of": "2026-10-23",
                    "expectancy": {"gates": {"passed": True}, "sample_size": 40},
                }
            ],
        }
        avail = summarize_board_availability(board)
        self.assertEqual(avail["code"], QUALIFYING)
        self.assertEqual(avail["buy_count"], 1)
        self.assertTrue(avail["research_only"])

    def test_no_qualifying_cash_regime(self):
        board = {
            "desk": "swing",
            "status": "cash",
            "message": "NIFTY below SMA50",
            "data_status": {"status": "FRESH", "latest_date": "2026-10-23"},
            "calls": [
                {
                    "symbol": "NIFTY",
                    "side": "HOLD",
                    "tags": ["CASH_WEEK"],
                    "as_of": "2026-10-23",
                }
            ],
        }
        avail = summarize_board_availability(board)
        self.assertEqual(avail["code"], NO_QUALIFYING)
        self.assertIn("strategy", avail["label"].lower())

    def test_data_blocked_stale_eod(self):
        board = {
            "desk": "swing",
            "status": "stale",
            "data_status": {"status": "STALE", "message": "EOD stale"},
            "calls": [{"symbol": "NIFTY", "side": "HOLD", "tags": ["STALE"]}],
        }
        avail = summarize_board_availability(board)
        self.assertEqual(avail["code"], DATA_BLOCKED)

    def test_data_blocked_feed_halt(self):
        board = {
            "desk": "intraday",
            "live_calls_allowed": False,
            "feed_health": {
                "live_calls_allowed": False,
                "market_data_state": "STALE",
                "message": "POST-MARKET freeze",
            },
            "calls": [
                {
                    "symbol": "RELIANCE",
                    "side": "HOLD",
                    "signal_generation": "halted",
                    "market_data_state": "STALE",
                    "tags": ["FEED_HALT"],
                }
            ],
        }
        avail = summarize_board_availability(board)
        self.assertEqual(avail["code"], DATA_BLOCKED)

    def test_gate_blocked_insufficient_history(self):
        board = {
            "desk": "intraday",
            "live_calls_allowed": True,
            "status": "ok",
            "calls": [
                {
                    "symbol": "INFY",
                    "side": "HOLD",
                    "expectancy": {
                        "insufficient_history": True,
                        "status_label": "insufficient_5m_history",
                        "gates": {
                            "passed": False,
                            "fail_reasons": ["INSUFFICIENT_5M_HISTORY"],
                        },
                    },
                }
            ],
        }
        avail = summarize_board_availability(board)
        self.assertEqual(avail["code"], GATE_BLOCKED)

    def test_stale_never_keeps_fresh_buy(self):
        call = annotate_call_display(
            {
                "symbol": "TCS",
                "side": "BUY",
                "badge": "STRONG_BUY",
                "market_data_state": "STALE",
                "signal_generation": "halted",
                "is_last_observation": True,
            },
            desk="intraday",
        )
        self.assertEqual(call["side"], "HOLD")
        self.assertEqual(call["badge"], "HOLD")
        self.assertEqual(call["data_status"], "STALE")
        self.assertEqual(call["desk"], "intraday")
        self.assertIn("gate_result", call)

    def test_attach_board_sets_availability(self):
        out = attach_board_availability(
            {
                "desk": "index",
                "strategy": "index_desk",
                "live_calls_allowed": True,
                "calls": [
                    {
                        "symbol": "^NSEI",
                        "side": "SELL",
                        "sources": ["index_mtf"],
                        "as_of": "2026-10-26T10:00:00+00:00",
                    }
                ],
            }
        )
        self.assertEqual(out["signal_availability"]["code"], QUALIFYING)
        self.assertEqual(out["calls"][0]["strategy"], "index_desk")
        self.assertEqual(out["calls"][0]["instrument"], "^NSEI")


class ExpectancyHonestySummaryTests(unittest.TestCase):
    def test_counts_insuff_proxy_gate(self):
        h = summarize_expectancy_honesty(
            [
                {
                    "symbol": "A",
                    "side": "HOLD",
                    "expectancy": {
                        "insufficient_history": True,
                        "status_label": "insufficient_5m_history",
                        "gates": {
                            "passed": False,
                            "fail_reasons": ["INSUFFICIENT_5M_HISTORY"],
                        },
                    },
                },
                {
                    "symbol": "B",
                    "side": "HOLD",
                    "expectancy": {
                        "proxy": True,
                        "status_label": "proxy_disabled",
                        "gates": {"passed": False, "fail_reasons": ["PROXY"]},
                    },
                },
                {
                    "symbol": "C",
                    "side": "BUY",
                    "expectancy": {
                        "gates": {"passed": True},
                        "proven": False,
                    },
                },
            ]
        )
        self.assertTrue(h["prominent"])
        self.assertEqual(h["insufficient_history_count"], 1)
        self.assertEqual(h["proxy_count"], 1)
        self.assertEqual(h["gate_failed_count"], 2)
        self.assertIn("INSUFFICIENT_5M_HISTORY", h["fail_reasons"])
        self.assertIn("5m history", h["detail"].lower())
        self.assertIn("proxy", h["detail"].lower())
        self.assertFalse(any("guarantee" in h["detail"].lower() for _ in [0]))

    def test_empty_board_not_prominent(self):
        h = summarize_expectancy_honesty([])
        self.assertFalse(h["prominent"])
        self.assertEqual(h["insufficient_history_count"], 0)

    def test_attach_board_includes_expectancy_honesty(self):
        out = attach_board_availability(
            {
                "desk": "intraday",
                "live_calls_allowed": True,
                "calls": [
                    {
                        "symbol": "TCS",
                        "side": "HOLD",
                        "expectancy": {
                            "insufficient_history": True,
                            "gates": {
                                "passed": False,
                                "fail_reasons": ["INSUFFICIENT_5M_HISTORY"],
                            },
                        },
                    }
                ],
            }
        )
        self.assertIn("expectancy_honesty", out)
        self.assertTrue(out["expectancy_honesty"]["prominent"])
        self.assertEqual(out["expectancy_honesty"]["insufficient_history_count"], 1)


class LedgerAvailabilityTests(unittest.TestCase):
    def test_demo_filtered(self):
        a = summarize_ledger_availability(
            published_count=0, filtered_demo_rows=4, category="swing"
        )
        self.assertEqual(a["code"], LEDGER_DEMO_FILTERED)
        # Must not instruct operators to run seed_platform
        self.assertNotRegex(a["detail"].lower(), r"run\s+seed_platform")
        self.assertIn("retired", a["detail"].lower())

    def test_empty_no_demo(self):
        a = summarize_ledger_availability(published_count=0, filtered_demo_rows=0)
        self.assertEqual(a["code"], LEDGER_EMPTY)
        self.assertIn("retired", a["detail"].lower())

    def test_has_published(self):
        a = summarize_ledger_availability(published_count=2, filtered_demo_rows=1)
        self.assertEqual(a["code"], LEDGER_HAS_ROWS)


class PlatformSignalsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_mod.config.auth_enabled = False
        cls.db_path = Path(_tmp.name)
        cls.pdb = PlatformDB(cls.db_path)
        cls.client = TestClient(app)

    def test_list_filters_demo_and_exposes_availability(self):
        from app.auth_deps import platform as platform_dep

        pdb = PlatformDB(Path(tempfile.mktemp(suffix=".db")))
        pdb.publish_signal(
            {
                "symbol": "DEMO1",
                "category": "swing",
                "direction": "buy",
                "timeframe": "1w",
                "status": "published",
                "rationale": "fixture demo",
                "data_mode": "demo",
            }
        )
        pdb.publish_signal(
            {
                "symbol": "LIVE1",
                "category": "swing",
                "direction": "buy",
                "timeframe": "1w",
                "status": "published",
                "rationale": "fixture live research",
                "data_mode": "delayed",
                "methodology_id": "weekly_swing",
                "provenance": {"source": "admin_publish"},
            }
        )

        app.dependency_overrides[platform_dep] = lambda: pdb
        try:
            r = self.client.get(
                "/api/platform/signals",
                params={"category": "swing", "history": True},
            )
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["count"], 1)
            self.assertEqual(body["filtered_demo_rows"], 1)
            self.assertEqual(body["ledger_availability"]["code"], LEDGER_HAS_ROWS)
            sig = body["signals"][0]
            self.assertEqual(sig["symbol"], "LIVE1")
            self.assertEqual(sig["desk"], "swing")
            self.assertEqual(sig["strategy"], "weekly_swing")
            self.assertEqual(sig["direction"], "BUY")
            self.assertEqual(sig["data_status"], "DELAYED")
            self.assertIn("gate_result", sig)
            self.assertNotIn("guarantee", (sig.get("rationale") or "").lower())
        finally:
            app.dependency_overrides.pop(platform_dep, None)

    def test_empty_ledger_demo_only(self):
        from app.auth_deps import platform as platform_dep

        pdb = PlatformDB(Path(tempfile.mktemp(suffix=".db")))
        pdb.publish_signal(
            {
                "symbol": "X",
                "category": "intraday",
                "direction": "none",
                "timeframe": "1d",
                "rationale": "demo",
                "data_mode": "demo",
            }
        )

        app.dependency_overrides[platform_dep] = lambda: pdb
        try:
            r = self.client.get(
                "/api/platform/signals",
                params={"category": "intraday", "history": True},
            )
            body = r.json()
            self.assertEqual(body["count"], 0)
            self.assertEqual(body["filtered_demo_rows"], 1)
            self.assertEqual(
                body["ledger_availability"]["code"], LEDGER_DEMO_FILTERED
            )
            self.assertIn("retired", body["ledger_availability"]["detail"].lower())
        finally:
            app.dependency_overrides.pop(platform_dep, None)


if __name__ == "__main__":
    unittest.main()
