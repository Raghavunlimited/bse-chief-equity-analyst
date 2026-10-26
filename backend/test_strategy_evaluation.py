"""Regression / quantitative tests for strategy evaluation honesty."""
from __future__ import annotations

import unittest

import pandas as pd
from fastapi.testclient import TestClient

from app import config as config_module
from app.expectancy.costs import DEFAULT_COSTS, r_multiple
from app.expectancy.gate import STRONG_GATES, _passes_gates
from app.expectancy.metrics import compute_edge_metrics
from app.expectancy.simulate import simulate_trade
from app.main import APP_VERSION, app
from app import strategy_evaluation as se


class LeakageTests(unittest.TestCase):
    def test_fill_is_next_open_not_signal_close(self):
        bars = pd.DataFrame(
            [
                {"trade_date": "2026-01-01", "open": 100, "high": 105, "low": 99, "close": 104},
                {"trade_date": "2026-01-02", "open": 103, "high": 110, "low": 102, "close": 108},
                {"trade_date": "2026-01-03", "open": 108, "high": 112, "low": 107, "close": 111},
            ]
        )
        chk = se.assert_no_lookahead_fill(
            bars, signal_entry=104, stop=95, target=120
        )
        self.assertTrue(chk["passed"], chk)
        sim = simulate_trade(
            bars, signal_entry=104, stop=95, target=120, side="BUY", max_hold=3
        )
        self.assertEqual(sim["entry_fill"], 103.0)
        self.assertNotEqual(sim["entry_fill"], 104.0)


class CostTests(unittest.TestCase):
    def test_costs_reduce_r_vs_zero_cost(self):
        # Winning long: entry 100 exit 110 stop 95
        with_costs = r_multiple(
            100, 110, 95, side="BUY", product="delivery", assumptions=DEFAULT_COSTS
        )
        zero = type(DEFAULT_COSTS)(
            brokerage_pct=0,
            brokerage_flat_cap=0,
            stt_sell_delivery_pct=0,
            exchange_txn_pct=0,
            sebi_turnover_pct=0,
            stamp_duty_buy_pct=0,
            gst_rate=0,
            slippage_pct_per_side=0,
            stt_sell_intraday_pct=0,
        )
        no_costs = r_multiple(100, 110, 95, side="BUY", product="delivery", assumptions=zero)
        self.assertIsNotNone(with_costs)
        self.assertIsNotNone(no_costs)
        self.assertLess(float(with_costs), float(no_costs))


class SampleSizeGateTests(unittest.TestCase):
    def test_gate_fails_small_n(self):
        trades = [{"r_multiple": 1.0}] * 10
        m = compute_edge_metrics(trades)
        ok, fails = _passes_gates({**m, "meta": {}, "rule_id": "elite_momentum"})
        self.assertFalse(ok)
        self.assertTrue(any("N<" in f for f in fails))

    def test_gate_thresholds_exported(self):
        self.assertEqual(STRONG_GATES["min_sample_size"], 30)
        self.assertEqual(STRONG_GATES["min_expectancy_r"], 0.25)
        self.assertEqual(STRONG_GATES["min_profit_factor"], 1.2)


class OosSplitTests(unittest.TestCase):
    def test_chronological_oos_split(self):
        trades = []
        for i, d in enumerate(
            ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-01-29"]
        ):
            trades.append({"date": d, "r_multiple": 0.5 if i % 2 == 0 else -0.5})
        split = se.split_trades_is_oos(trades, oos_fraction=0.4)
        self.assertEqual(split["split"], "chronological_by_date")
        self.assertGreater(len(split["out_of_sample"]), 0)
        self.assertGreater(len(split["in_sample"]), 0)
        # OOS dates are the latest
        self.assertEqual(max(split["oos_dates"]), "2026-01-29")
        is_dates = set(split["is_dates"])
        oos_dates = set(split["oos_dates"])
        self.assertFalse(is_dates & oos_dates)


class OptionsHonestyTests(unittest.TestCase):
    def test_put_call_not_directional_from_oi_pcr(self):
        out = se.options_put_call_evaluation()
        self.assertFalse(out["evaluable"])
        self.assertFalse(out["oi_pcr_directional_signal"])
        self.assertFalse(out["explicit_rules_defined"])
        self.assertIsNone(out["entry_invalidation_stop_targets_exit"])
        self.assertFalse(out["proven"])


class UniverseHonestyTests(unittest.TestCase):
    def test_report_states_current_universe_and_is_not_proven(self):
        import tempfile
        from pathlib import Path

        from app.store import Database

        with tempfile.TemporaryDirectory() as td:
            report = se.build_evaluation_report(
                Database(Path(td) / "eval.db"),
                run_harness=False,
            )
        text = report["universe_honesty"]
        self.assertIn("current stored list", text)
        self.assertIn("delisted names are absent", text)
        self.assertNotIn("proven", text.lower())
        self.assertNotIn("solved", text.lower())
        self.assertFalse(report["proven"])
        for ev in report["evaluations"]:
            self.assertFalse(ev.get("proven", False))


class ConsistencyTests(unittest.TestCase):
    def test_evaluate_bundle_never_best_or_proven(self):
        trades = [
            {"date": "2026-01-01", "r_multiple": 1.0, "regime": "BULL"},
            {"date": "2026-01-08", "r_multiple": -0.5, "regime": "BULL"},
            {"date": "2026-01-15", "r_multiple": 0.8, "regime": "BEAR"},
            {"date": "2026-01-22", "r_multiple": -0.2, "regime": "BEAR"},
        ]
        ev = se.evaluate_trades_bundle(
            trades,
            rule_id="elite_momentum",
            meta={"strategy_version": se.STRATEGY_VERSION},
        )
        self.assertFalse(ev["proven"])
        self.assertFalse(ev["best"])
        self.assertIn("out_of_sample", ev)
        self.assertIn("by_regime", ev)
        self.assertIn("risk", ev)
        self.assertIn("gates", ev)

    def test_bias_checklist_does_not_claim_clean(self):
        b = se.bias_checklist()
        self.assertFalse(b["multiple_testing"]["selects_best"])
        self.assertIn("residual_risk", b["survivorship_bias"])
        self.assertIn("mitigated", b["look_ahead_bias"]["status"])


class ApiTests(unittest.TestCase):
    def test_evaluate_requires_key_only_when_api_key_is_configured(self):
        from app.security import path_requires_api_key

        self.assertTrue(
            path_requires_api_key("POST", "/api/strategy-evaluation/evaluate")
        )
        self.assertTrue(
            path_requires_api_key(
                "GET", "/api/strategy-evaluation", run_harness="true"
            )
        )
        self.assertFalse(
            path_requires_api_key(
                "GET", "/api/strategy-evaluation", run_harness="false"
            )
        )
        self.assertFalse(path_requires_api_key("GET", "/api/strategy-evaluation/meta"))

        old_api_key = config_module.config.api_key
        try:
            client = TestClient(app)
            object.__setattr__(config_module.config, "api_key", "test-evaluate-key")
            blocked = client.post(
                "/api/strategy-evaluation/evaluate",
                json={"run_harness": False},
            )
            self.assertEqual(blocked.status_code, 401)
            self.assertEqual(blocked.json()["detail"], "Invalid or missing X-API-Key")
            # Never leak key material
            self.assertNotIn("test-evaluate-key", blocked.text)

            wrong = client.post(
                "/api/strategy-evaluation/evaluate",
                json={"run_harness": False},
                headers={"X-API-Key": "wrong-key"},
            )
            self.assertEqual(wrong.status_code, 401)

            ok = client.post(
                "/api/strategy-evaluation/evaluate",
                json={"run_harness": False},
                headers={"X-API-Key": "test-evaluate-key"},
            )
            self.assertEqual(ok.status_code, 200)
            self.assertNotIn("api_key", ok.json())
            self.assertNotIn("test-evaluate-key", ok.text)

            # Read-only / cheap GETs stay open when key is configured
            for path in (
                "/api/strategy-evaluation/meta",
                "/api/strategy-evaluation/audit",
                "/api/strategy-evaluation?run_harness=false",
            ):
                r = client.get(path)
                self.assertEqual(r.status_code, 200, path)

            # Expensive GET harness matches POST evaluate gate
            harness_blocked = client.get(
                "/api/strategy-evaluation",
                params={"run_harness": True},
            )
            self.assertEqual(harness_blocked.status_code, 401)
            harness_ok = client.get(
                "/api/strategy-evaluation",
                params={"run_harness": True},
                headers={"X-API-Key": "test-evaluate-key"},
            )
            self.assertEqual(harness_ok.status_code, 200)

            object.__setattr__(config_module.config, "api_key", "")
            open_route = client.post(
                "/api/strategy-evaluation/evaluate",
                json={"run_harness": False},
            )
            self.assertEqual(open_route.status_code, 200)
        finally:
            object.__setattr__(config_module.config, "api_key", old_api_key)

    def test_version_meta_and_summary(self):
        self.assertTrue(
            "strategy-eval" in APP_VERSION or APP_VERSION.startswith("5.12"),
            APP_VERSION,
        )
        c = TestClient(app)
        meta = c.get("/api/strategy-evaluation/meta")
        self.assertEqual(meta.status_code, 200)
        body = meta.json()
        self.assertFalse(body["selects_best"])
        self.assertFalse(body["proven"])
        self.assertFalse(body["honesty"]["oi_pcr_directional"])
        self.assertIn("catalog", body)

        audit = c.get("/api/strategy-evaluation/audit")
        self.assertEqual(audit.status_code, 200)
        self.assertIn("candidates", audit.json())

        # Stored-metrics path (no slow harness)
        summary = c.get(
            "/api/strategy-evaluation",
            params={"run_harness": "false"},
        )
        self.assertEqual(summary.status_code, 200)
        s = summary.json()
        self.assertFalse(s["selects_best"])
        self.assertFalse(s["proven"])
        self.assertIn("bias_checklist", s)
        self.assertIn("baselines", s)
        self.assertIn("evaluations", s)
        self.assertIn("limitations", s)
        # No evaluation marked best/proven
        for ev in s["evaluations"]:
            self.assertFalse(ev.get("proven", False))
            self.assertFalse(ev.get("best", False))
        # Options entry present and non-directional
        opt = next(
            e for e in s["evaluations"] if e.get("rule_id") == "options_put_call_setup"
        )
        self.assertFalse(opt.get("oi_pcr_directional_signal", True))

        root = c.get("/").json()
        self.assertIn("strategy_evaluation", root)


if __name__ == "__main__":
    unittest.main()
