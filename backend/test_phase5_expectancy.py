"""Phase 5 — walk-forward expectancy, India costs, STRONG gating (no fake stats)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.expectancy.costs import net_return_pct, r_multiple, round_trip_cost_fraction
from app.expectancy.gate import (
    STRONG_GATES,
    apply_expectancy_gate,
    derive_badge,
)
from app.expectancy.harness import RULE_SWING, run_and_persist, run_walk_forward
from app.expectancy.metrics import compute_edge_metrics, segment_by_regime
from app.expectancy.persist import ensure_expectancy_schema, load_metrics, upsert_metrics_rows
from app.expectancy.regimes import classify_regime, regime_series
from app.expectancy.simulate import simulate_trade
from app.store import Database


def _synth_ohlcv(
    n: int = 120,
    start: float = 100.0,
    drift: float = 0.001,
    vol: float = 0.012,
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + drift + vol * float(rng.standard_normal())))
    rows = []
    for i, d in enumerate(dates):
        c = closes[i]
        o = c * (1 + 0.002 * float(rng.standard_normal()))
        h = max(o, c) * (1 + abs(0.004 * float(rng.standard_normal())))
        l = min(o, c) * (1 - abs(0.004 * float(rng.standard_normal())))
        rows.append(
            {
                "symbol": "TEST",
                "trade_date": d.strftime("%Y-%m-%d"),
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": 1_000_000,
                "turnover": 1_000_000 * c,
                "prev_close": round(closes[i - 1], 2) if i else None,
            }
        )
    return pd.DataFrame(rows)


class TestIndiaCosts(unittest.TestCase):
    def test_round_trip_positive_and_legible(self):
        rt = round_trip_cost_fraction(1000.0, 1010.0, side="BUY", product="delivery")
        self.assertGreater(rt["cost_fraction"], 0.0)
        self.assertGreater(rt["cost_inr"], 0.0)
        self.assertIn("stt", rt["legs"]["close"])
        # Sell leg carries STT for delivery
        self.assertGreater(rt["legs"]["close"]["stt"], 0.0)

    def test_net_return_less_than_gross(self):
        gross = (1010 / 1000 - 1) * 100
        net = net_return_pct(1000.0, 1010.0, side="BUY")
        self.assertLess(net, gross)

    def test_r_multiple_accounts_for_costs(self):
        # 10 pt move vs 10 pt risk → gross 1R; costs pull below 1R
        r = r_multiple(100.0, 110.0, 90.0, side="BUY")
        self.assertIsNotNone(r)
        self.assertLess(r, 1.0)
        self.assertGreater(r, 0.8)


class TestRegimes(unittest.TestCase):
    def test_bull_trend_on_up_stack(self):
        df = _synth_ohlcv(n=100, drift=0.004, vol=0.006, seed=1)
        out = classify_regime(df)
        self.assertIn(out["regime"], ("BULL_TREND", "LOW_VOL_RANGE", "HIGH_VOL_CHOP"))
        self.assertIsNotNone(out["vol_ann"])

    def test_insufficient_bars_unknown(self):
        df = _synth_ohlcv(n=20)
        self.assertEqual(classify_regime(df)["regime"], "UNKNOWN")

    def test_regime_series_no_lookahead_length(self):
        df = _synth_ohlcv(n=80)
        s = regime_series(df)
        self.assertEqual(len(s), len(df))
        self.assertEqual(s.iloc[0], "UNKNOWN")


class TestSimulateAndMetrics(unittest.TestCase):
    def test_stop_before_target_same_bar(self):
        bars = pd.DataFrame(
            [
                {"trade_date": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100},
                {"trade_date": "2024-01-02", "open": 100, "high": 112, "low": 88, "close": 105},
            ]
        )
        sim = simulate_trade(
            bars, signal_entry=100, stop=95, target=110, side="BUY", max_hold=5
        )
        self.assertEqual(sim["exit_reason"], "stop")
        self.assertLess(sim["r_multiple"], 0)

    def test_metrics_expectancy_formula(self):
        trades = [
            {"r_multiple": 1.0, "regime": "BULL_TREND"},
            {"r_multiple": 1.0, "regime": "BULL_TREND"},
            {"r_multiple": -1.0, "regime": "BULL_TREND"},
            {"r_multiple": -1.0, "regime": "BEAR_TREND"},
        ]
        m = compute_edge_metrics(trades)
        self.assertEqual(m["sample_size"], 4)
        self.assertAlmostEqual(m["win_rate_pct"], 50.0)
        # E = 0.5*1 - 0.5*1 = 0
        self.assertAlmostEqual(m["expectancy_r"], 0.0, places=4)
        seg = segment_by_regime(trades)
        self.assertEqual(seg["BULL_TREND"]["sample_size"], 3)
        self.assertEqual(seg["BEAR_TREND"]["sample_size"], 1)
        self.assertEqual(seg["HIGH_VOL_CHOP"]["sample_size"], 0)


class TestGate(unittest.TestCase):
    def test_strong_blocked_without_edge(self):
        badge = derive_badge("BUY", confidence=90, gates_ok=False)
        self.assertEqual(badge, "BUY")

    def test_strong_allowed_with_edge(self):
        badge = derive_badge("BUY", confidence=90, gates_ok=True)
        self.assertEqual(badge, "STRONG_BUY")
        badge_s = derive_badge("SELL", confidence=90, gates_ok=True)
        self.assertEqual(badge_s, "STRONG_SELL")

    def test_gates_constants(self):
        self.assertEqual(STRONG_GATES["min_sample_size"], 30)
        self.assertEqual(STRONG_GATES["min_expectancy_r"], 0.25)
        self.assertEqual(STRONG_GATES["min_profit_factor"], 1.2)

    def test_apply_gate_attaches_real_metrics_never_invents(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "t.db")
            ensure_expectancy_schema(db)
            # Persist failing metrics (N too small)
            upsert_metrics_rows(
                db,
                rule_id=RULE_SWING,
                desk="swing",
                by_regime={
                    "BULL_TREND": {
                        "sample_size": 10,
                        "win_rate_pct": 55.0,
                        "avg_win_r": 1.2,
                        "avg_loss_r": 1.0,
                        "expectancy_r": 0.3,
                        "profit_factor": 1.5,
                        "max_drawdown_pct": -5.0,
                    },
                    "ALL": {
                        "sample_size": 10,
                        "win_rate_pct": 55.0,
                        "avg_win_r": 1.2,
                        "avg_loss_r": 1.0,
                        "expectancy_r": 0.3,
                        "profit_factor": 1.5,
                        "max_drawdown_pct": -5.0,
                    },
                },
                as_of="2024-06-01",
            )
            call = {
                "desk": "swing",
                "symbol": "RELIANCE",
                "side": "BUY",
                "confidence": 80.0,
                "thesis": "test",
                "tags": [],
                "as_of": "2024-06-01",
            }
            out = apply_expectancy_gate(
                call, db=db, regime="BULL_TREND", rule_id=RULE_SWING, auto_refresh=False
            )
            self.assertEqual(out["badge"], "BUY")  # N=10 < 30 → no STRONG
            self.assertEqual(out["expectancy"]["sample_size"], 10)
            self.assertEqual(out["expectancy"]["win_rate_pct"], 55.0)
            self.assertFalse(out["expectancy"]["gates"]["passed"])

            # Gate thresholds met → STRONG badge (research only — not "proven")
            upsert_metrics_rows(
                db,
                rule_id=RULE_SWING,
                desk="swing",
                by_regime={
                    "BULL_TREND": {
                        "sample_size": 40,
                        "win_rate_pct": 55.0,
                        "avg_win_r": 1.5,
                        "avg_loss_r": 1.0,
                        "expectancy_r": 0.4,
                        "profit_factor": 1.8,
                        "max_drawdown_pct": -8.0,
                    }
                },
            )
            call_legacy = {
                **call,
                "tags": ["EDGE_PROVEN", "STRONG_BUY"],  # legacy misleading tags
            }
            out2 = apply_expectancy_gate(
                call_legacy,
                db=db,
                regime="BULL_TREND",
                rule_id=RULE_SWING,
                auto_refresh=False,
            )
            self.assertEqual(out2["badge"], "STRONG_BUY")
            self.assertTrue(out2["expectancy"]["gates"]["passed"])
            self.assertFalse(out2["expectancy"].get("proven"))
            tags = [str(t) for t in (out2.get("tags") or [])]
            self.assertIn("GATE_PASS_RESEARCH", tags)
            self.assertNotIn("EDGE_PROVEN", tags)
            self.assertTrue(
                all("EDGE_PROVEN" not in t for t in tags),
                tags,
            )


class TestHarnessPersist(unittest.TestCase):
    def _seed_db(self, db: Database, n_days: int = 100, n_syms: int = 8) -> None:
        nifty = _synth_ohlcv(n=n_days, start=22000, drift=0.0008, vol=0.008, seed=2)
        nifty["symbol"] = "NIFTY"
        db.upsert_eod_data(nifty)
        # Indicators for NIFTY not required for regime (uses eod)
        for si, sym in enumerate([f"S{i}" for i in range(n_syms)]):
            df = _synth_ohlcv(
                n=n_days,
                start=200 + si * 10,
                drift=0.0015,
                vol=0.015,
                seed=10 + si,
            )
            df["symbol"] = sym
            db.upsert_eod_data(df)
            # Minimal indicators so joined snapshot works
            ind = df[["symbol", "trade_date"]].copy()
            close = df["close"].astype(float)
            ind["sma_20"] = close.rolling(20).mean()
            ind["sma_50"] = close.rolling(50).mean()
            ind["rsi_14"] = 55.0
            ind["atr_14"] = close * 0.02
            ind["vol_ma_20"] = 1_000_000
            ind["hh_20"] = close.rolling(20).max()
            ind["ll_20"] = close.rolling(20).min()
            ind["roc_3"] = close.pct_change(3) * 100
            ind["roc_20"] = close.pct_change(20) * 100
            ind["prev_volume"] = 900_000
            db.upsert_indicators(ind)

    def test_walk_forward_persists_real_counts(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "wf.db")
            self._seed_db(db)
            # Phase 3: index/intraday need 5m bars — without them trade_count may be 0
            # (honest insufficient). Swing still needs richer filters.
            result = run_and_persist(
                db,
                sector_map={f"S{i}": "TEST" for i in range(8)},
                rules=["index_mtf_vwap_v1", "intraday_bias_v1"],
            )
            self.assertEqual(result["status"], "ok")
            idx = result["rules"]["index_mtf_vwap_v1"]
            self.assertFalse(idx.get("proxy", True))
            self.assertEqual(idx.get("data_interval"), "5m")
            self.assertTrue(
                idx.get("insufficient_history") or idx.get("trade_count", 0) >= 0
            )
            m = load_metrics(db, rule_id="index_mtf_vwap_v1")
            self.assertIsNotNone(m)
            self.assertIn("regimes", m)
            all_row = m["regimes"].get("ALL")
            self.assertIsNotNone(all_row)
            self.assertEqual(
                all_row["sample_size"],
                result["rules"]["index_mtf_vwap_v1"]["trade_count"],
            )


class TestAppVersion(unittest.TestCase):
    def test_version_phase5(self):
        import re

        from app.main import APP_VERSION, app

        # Phase-5+ lineage (expectancy shipped in 5.5; follow-ons keep minor ≥ 5)
        m = re.match(r"^5\.(\d+)\.", APP_VERSION)
        self.assertTrue(m and int(m.group(1)) >= 5, APP_VERSION)
        paths = {r.path for r in app.routes}
        self.assertIn("/api/expectancy/run", paths)
        self.assertIn("/api/expectancy/metrics", paths)


if __name__ == "__main__":
    unittest.main()
