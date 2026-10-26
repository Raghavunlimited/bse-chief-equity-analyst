"""Deterministic tests for risk-based position sizing (research calc only)."""
from __future__ import annotations

import unittest

from app import position_sizing as ps
from app.main import APP_VERSION, app
from fastapi.testclient import TestClient


class RiskBudgetTests(unittest.TestCase):
    def test_equity_risk_budget_and_shares(self):
        # capital 100_000, risk 1% → 1000; entry 100 stop 90 → 10/share → 100 shares
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            direction="LONG",
            instrument_kind="EQ",
            contract_mapping_verified=True,
            lot_size_verified=True,
            lot_size=1,
            multiplier=1,
            contract_source="test_cash_eq",
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["units"], 100)
        self.assertEqual(out["size"]["lots"], 100)
        self.assertEqual(out["size"]["risk_rs"], 1000.0)
        self.assertFalse(out["is_order_instruction"])
        self.assertIn("formula", out)
        self.assertTrue(out["assumptions"])

    def test_fixed_costs_reduce_budget(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=True,
            fixed_costs=200,  # budget 800 → 80 shares
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["units"], 80)

    def test_cost_per_unit_widens_risk(self):
        # per_unit = 10 + 2 = 12; budget 1000 → floor(1000/12)=83
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=True,
            cost_per_unit=2.0,
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["units"], 83)

    def test_round_trip_cost_pct(self):
        # price risk 10 + 100*0.1% = 10.1; floor(1000/10.1)=99
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=True,
            round_trip_cost_pct=0.1,
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["units"], 99)


class LotRoundingTests(unittest.TestCase):
    def test_floor_to_lot(self):
        # budget 1000, risk/share 10 → 100 shares; lot 75 → 1 lot = 75
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            lot_size=75,
            lot_size_verified=True,
            contract_mapping_verified=True,
            multiplier=1,
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["lots"], 1)
        self.assertEqual(out["size"]["units"], 75)

    def test_exposure_cap_max_lots(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=True,
            max_lots=50,
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["lots"], 50)
        self.assertIn("max_lots", out["size"]["caps_applied"])

    def test_max_position_pct(self):
        # risk wants 100 shares @100 = 10k; max 5% of 100k = 5k → 50 shares
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=True,
            max_position_pct=5.0,
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["units"], 50)
        self.assertIn("max_position_pct", out["size"]["caps_applied"])


class ContractMappingTests(unittest.TestCase):
    def test_unverified_mapping_blocks(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=False,
        )
        self.assertFalse(out["available"])
        self.assertIsNone(out["size"])
        self.assertIn("contract_mapping_unverified", out["blockers"])

    def test_fut_requires_verified_lot_and_margin(self):
        out = ps.calculate_size(
            capital=500_000,
            risk_pct=1.0,
            entry=24_500,
            stop=24_000,
            instrument_kind="FUT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            # margin missing
        )
        self.assertFalse(out["available"])
        self.assertIn("margin_per_lot_missing", out["blockers"])

        ok = ps.calculate_size(
            capital=500_000,
            risk_pct=1.0,
            entry=24_500,
            stop=24_000,
            instrument_kind="FUT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            margin_per_lot=120_000,
            margin_verified=True,
            contract_source="kotak_scrip_master_test",
        )
        self.assertTrue(ok["available"], ok)
        # risk/lot = 500*25 = 12_500; budget 5000 → 0 lots
        # Wait: capital 500k * 1% = 5000; per_lot = 500*25 = 12500 → 0 lots
        self.assertEqual(ok["size"]["lots"], 0)

        ok2 = ps.calculate_size(
            capital=2_000_000,
            risk_pct=1.0,
            entry=24_500,
            stop=24_000,
            instrument_kind="FUT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            margin_per_lot=120_000,
            margin_verified=True,
        )
        # budget 20_000 / 12_500 = 1 lot
        self.assertEqual(ok2["size"]["lots"], 1)
        self.assertEqual(ok2["size"]["units"], 25)

    def test_unverified_fut_lot_blocks(self):
        out = ps.calculate_size(
            capital=2_000_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="FUT",
            lot_size=50,
            multiplier=1,
            lot_size_verified=False,
            contract_mapping_verified=True,
            margin_per_lot=10_000,
            margin_verified=True,
        )
        self.assertFalse(out["available"])
        self.assertIn("lot_size_unverified", out["blockers"])

    def test_mcx_proxy_unavailable(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=2000,
            stop=1980,
            instrument_kind="MCX_PROXY",
            contract_mapping_verified=True,
            lot_size_verified=True,
            lot_size=1,
            multiplier=1,
        )
        self.assertFalse(out["available"])
        self.assertIsNone(out["size"])
        self.assertTrue(
            any("mcx" in b for b in out["blockers"]),
            out["blockers"],
        )


class OptionsTests(unittest.TestCase):
    def test_long_option_full_premium_risk(self):
        # premium 100, lot 25, mult 1 → per_lot risk 2500; budget 10_000 → 4 lots
        out = ps.calculate_size(
            capital=1_000_000,
            risk_pct=1.0,
            entry=100,
            stop=None,
            direction="LONG",
            instrument_kind="OPT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            option_right="CE",
            option_premium=100,
            contract_source="kotak_scrip_master_test",
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["lots"], 4)
        self.assertEqual(out["size"]["units"], 100)

    def test_long_option_with_stop(self):
        # premium 100 stop 60 → risk 40 * 25 = 1000/lot; budget 10k → 10 lots
        out = ps.calculate_size(
            capital=1_000_000,
            risk_pct=1.0,
            entry=100,
            stop=60,
            direction="LONG",
            instrument_kind="OPT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            option_premium=100,
        )
        self.assertTrue(out["available"], out)
        self.assertEqual(out["size"]["lots"], 10)

    def test_short_option_needs_margin(self):
        out = ps.calculate_size(
            capital=1_000_000,
            risk_pct=1.0,
            entry=100,
            stop=140,
            direction="SHORT",
            instrument_kind="OPT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            option_premium=100,
        )
        self.assertFalse(out["available"])
        self.assertIn("margin_per_lot_missing", out["blockers"])

        ok = ps.calculate_size(
            capital=1_000_000,
            risk_pct=1.0,
            entry=100,
            stop=140,
            direction="SHORT",
            instrument_kind="OPT",
            lot_size=25,
            multiplier=1,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            option_premium=100,
            margin_per_lot=80_000,
            margin_verified=True,
        )
        self.assertTrue(ok["available"], ok)
        # risk/lot = 40*25 = 1000; budget 10k → 10; margin cap floor(1e6/8e4)=12 → 10
        self.assertEqual(ok["size"]["lots"], 10)

    def test_options_unverified_multiplier_blocks(self):
        out = ps.calculate_size(
            capital=1_000_000,
            risk_pct=1.0,
            entry=100,
            direction="LONG",
            instrument_kind="OPT",
            lot_size=25,
            multiplier=None,
            lot_size_verified=True,
            contract_mapping_verified=True,
            expiry="2026-10-29",
            option_premium=100,
        )
        self.assertFalse(out["available"])
        self.assertIn("multiplier_missing", out["blockers"])


class UnavailableInputTests(unittest.TestCase):
    def test_missing_stop_equity(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=None,
            instrument_kind="EQ",
            contract_mapping_verified=True,
        )
        self.assertFalse(out["available"])
        self.assertIn("stop_missing", out["blockers"])
        self.assertIsNone(out["size"])

    def test_stale_quote_blocks(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=90,
            instrument_kind="EQ",
            contract_mapping_verified=True,
            quote_stale=True,
        )
        self.assertFalse(out["available"])
        self.assertIn("quote_or_inputs_stale", out["blockers"])

    def test_bad_stop_direction(self):
        out = ps.calculate_size(
            capital=100_000,
            risk_pct=1.0,
            entry=100,
            stop=110,
            direction="LONG",
            instrument_kind="EQ",
            contract_mapping_verified=True,
        )
        self.assertFalse(out["available"])
        self.assertIn("stop_not_below_entry_for_long", out["blockers"])


class ApiTests(unittest.TestCase):
    def test_version_and_endpoints(self):
        from app.version_assert import minor_at_least

        self.assertTrue(minor_at_least(APP_VERSION, 10), APP_VERSION)
        c = TestClient(app)
        meta = c.get("/api/position-sizing/meta")
        self.assertEqual(meta.status_code, 200)
        self.assertIn("research", meta.json()["disclaimer"].lower())
        self.assertFalse(meta.json()["is_order_instruction"])

        r = c.post(
            "/api/position-sizing/calculate",
            json={
                "capital": 100000,
                "risk_pct": 1,
                "entry": 100,
                "stop": 90,
                "instrument_kind": "EQ",
                "contract_mapping_verified": True,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["available"])
        self.assertEqual(body["size"]["units"], 100)
        self.assertIn("formula", body)
        self.assertFalse(body["is_order_instruction"])

        blocked = c.post(
            "/api/position-sizing/calculate",
            json={
                "capital": 100000,
                "risk_pct": 1,
                "entry": 100,
                "stop": 90,
                "instrument_kind": "EQ",
                "contract_mapping_verified": False,
            },
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertFalse(blocked.json()["available"])
        self.assertIsNone(blocked.json()["size"])

    def test_root_lists_sizing(self):
        c = TestClient(app)
        root = c.get("/").json()
        self.assertIn("position_sizing", root)


if __name__ == "__main__":
    unittest.main()
