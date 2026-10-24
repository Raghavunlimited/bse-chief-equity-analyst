#!/usr/bin/env python3
"""Unit tests for baseline_v1 signal methodology — no network."""
from __future__ import annotations

import unittest

from app.signals.methodology import METHODOLOGY_ID, apply_baseline, score_evidence


class MethodologyTests(unittest.TestCase):
    def test_empty_evidence_is_none_insufficient(self):
        r = score_evidence({})
        self.assertEqual(r["direction"], "none")
        self.assertTrue(r["insufficient"])
        self.assertEqual(r["methodology_id"], METHODOLOGY_ID)

    def test_single_field_insufficient(self):
        r = score_evidence({"rsi_14": 55})
        self.assertEqual(r["direction"], "none")
        self.assertTrue(r["insufficient"])

    def test_buy_when_rsi_and_price_constructive(self):
        r = score_evidence(
            {"rsi_14": 58, "close": 100, "sma_20": 95, "volume_ratio": 2.0}
        )
        self.assertEqual(r["direction"], "buy")
        self.assertFalse(r["insufficient"])
        self.assertGreaterEqual(r["score"], 50)

    def test_sell_when_extended_rsi_and_below_sma(self):
        r = score_evidence(
            {"rsi_14": 75, "close": 90, "sma_20": 100, "volume_ratio": 1.0}
        )
        self.assertEqual(r["direction"], "sell")
        self.assertFalse(r["insufficient"])

    def test_tie_bull_bear_yields_none(self):
        # RSI constructive (+bull) but close below SMA (+bear) → tie → none
        r = score_evidence({"rsi_14": 55, "close": 90, "sma_20": 100})
        self.assertEqual(r["direction"], "none")
        self.assertTrue(r["insufficient"])

    def test_non_numeric_rsi_ignored_not_crash(self):
        r = score_evidence({"rsi_14": "bad", "close": 110, "sma_20": 100})
        # only price field counts → fields_present=1 → insufficient
        self.assertEqual(r["direction"], "none")
        self.assertTrue(r["insufficient"])

    def test_oi_counts_only_when_available_true(self):
        thin = score_evidence({"rsi_14": 55, "oi_available": False, "oi_change": 10})
        self.assertTrue(thin["insufficient"])
        ok = score_evidence(
            {
                "rsi_14": 55,
                "oi_available": True,
                "oi_change": 10,
            }
        )
        # rsi + oi = 2 fields; bull from rsi only → buy
        self.assertEqual(ok["direction"], "buy")

    def test_apply_baseline_timeframes_and_risk_notes(self):
        for cat, tf in (("intraday", "session"), ("swing", "1w"), ("commodity", "1d")):
            out = apply_baseline(
                "reli",
                cat,
                {"rsi_14": 50},
                data_mode="demo",
            )
            self.assertEqual(out["symbol"], "RELI")
            self.assertEqual(out["timeframe"], tf)
            self.assertEqual(out["data_mode"], "demo")
            self.assertIn("not performance-verified", out["risk_notes"].lower())
            self.assertEqual(out["direction"], "none")


if __name__ == "__main__":
    unittest.main()
