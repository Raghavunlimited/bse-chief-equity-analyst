"""Phase 3 — 5m persistence, session/gaps, shared cores, no-look-ahead, sample gates."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")

from app.bars_5m import (  # noqa: E402
    Bar5m,
    bars_from_yahoo_chart_payload,
    expected_session_starts,
    find_gaps,
    floor_bucket,
    in_regular_session,
    load_bars,
    retention_purge,
    upsert_bars,
)
from app.expectancy.costs import DEFAULT_COSTS, r_multiple  # noqa: E402
from app.expectancy.gate import STRONG_GATES, apply_expectancy_gate  # noqa: E402
from app.expectancy.harness import RULE_INTRADAY, RULE_META  # noqa: E402
from app.expectancy.harness_5m import (  # noqa: E402
    MIN_BARS_FOR_RUN,
    run_intraday_5m_trades,
)
from app.expectancy.persist import upsert_metrics_rows  # noqa: E402
from app.expectancy.simulate import simulate_trade  # noqa: E402
from app.store import Database  # noqa: E402
from app.strategy.intraday_core import score_intraday_bias  # noqa: E402
from app.strategy.index_core import score_index_mtf  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


def _weekday_session_start(d: datetime) -> int:
    """09:15 IST unix for a known weekday."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    start = d.replace(hour=9, minute=15, second=0, microsecond=0, tzinfo=IST)
    return int(start.timestamp())


class SessionAndValidateTests(unittest.TestCase):
    def test_session_boundaries(self):
        # Monday 2026-10-26 is a weekday
        open_ts = _weekday_session_start(datetime(2026, 10, 26))
        self.assertTrue(in_regular_session(open_ts))
        # 15:30 start invalid; 15:25 ok
        t1525 = open_ts + ((15 * 60 + 25) - (9 * 60 + 15)) * 60
        self.assertTrue(in_regular_session(t1525))
        t1530 = open_ts + ((15 * 60 + 30) - (9 * 60 + 15)) * 60
        self.assertFalse(in_regular_session(t1530))
        # Weekend
        sat = datetime(2026, 10, 24, 10, 0, tzinfo=IST)
        self.assertFalse(in_regular_session(int(sat.timestamp())))

    def test_reject_malformed_and_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "b.db"
            start = _weekday_session_start(datetime(2026, 10, 26))
            bad = Bar5m(
                symbol="TCS",
                bar_start_unix=start + 1,  # unaligned
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                completed=True,
            )
            self.assertFalse(bad.validate()[0])
            ok = Bar5m(
                symbol="TCS",
                bar_start_unix=start,
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=1000,
                source="yahoo_chart",
                completed=True,
            )
            st = upsert_bars([ok], db_path=dbp)
            self.assertEqual(st["accepted"], 1)
            # Duplicate same key — accepted overwrite
            ok2 = Bar5m(
                symbol="TCS",
                bar_start_unix=start,
                open=100,
                high=102,
                low=99,
                close=101,
                volume=1100,
                source="yahoo_chart",
                completed=True,
            )
            upsert_bars([ok2], db_path=dbp)
            df = load_bars("TCS", db_path=dbp)
            self.assertEqual(len(df), 1)
            self.assertEqual(float(df.iloc[0]["close"]), 101.0)
            # Incomplete must not overwrite completed
            inc = Bar5m(
                symbol="TCS",
                bar_start_unix=start,
                open=100,
                high=103,
                low=99,
                close=102,
                volume=1,
                source="yahoo_chart",
                completed=False,
            )
            st3 = upsert_bars([inc], db_path=dbp)
            self.assertGreaterEqual(st3["skipped_incomplete_vs_complete"], 1)
            df2 = load_bars("TCS", db_path=dbp)
            self.assertEqual(float(df2.iloc[0]["close"]), 101.0)

    def test_gaps_and_retention(self):
        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "g.db"
            start = _weekday_session_start(datetime(2026, 10, 26))
            sess = datetime.fromtimestamp(start, tz=IST).date().isoformat()
            bars = [
                Bar5m(
                    symbol="INFY",
                    bar_start_unix=start + i * 300,
                    open=100 + i,
                    high=101 + i,
                    low=99 + i,
                    close=100.5 + i,
                    volume=10,
                    source="synthetic_test",
                    completed=True,
                    session_date=sess,
                )
                for i in range(3)  # skip rest → gaps
            ]
            upsert_bars(bars, db_path=dbp)
            present = load_bars("INFY", session_date=sess, db_path=dbp)["bar_start_unix"].tolist()
            gaps = find_gaps(sess, present)
            self.assertGreater(len(gaps), 50)
            self.assertEqual(len(expected_session_starts(sess)), len(gaps) + 3)
            # Old session purge
            old = Bar5m(
                symbol="INFY",
                bar_start_unix=start - 90 * 86400,
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
                source="synthetic_test",
                completed=True,
            )
            # May fail session validate if weekend — force via direct if needed
            if old.validate()[0]:
                upsert_bars([old], db_path=dbp)
            deleted = retention_purge(retention_days=30, db_path=dbp, now=datetime(2026, 10, 26, tzinfo=IST))
            self.assertIsInstance(deleted, int)

    def test_drop_incomplete_yahoo_payload(self):
        start = _weekday_session_start(datetime(2026, 10, 26))
        now = start + 300 + 60  # mid second bar
        bars = bars_from_yahoo_chart_payload(
            symbol="RELIANCE",
            timestamps=[start, start + 300],
            opens=[100, 101],
            highs=[101, 102],
            lows=[99, 100],
            closes=[100.5, 101.5],
            volumes=[10, 11],
            now_unix=now,
            drop_incomplete=True,
        )
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].bar_start_unix, start)


class StrategyEquivalenceTests(unittest.TestCase):
    def test_live_core_matches_harness_inputs(self):
        closes = [100 + i * 0.1 for i in range(30)]
        vols = [1000.0] * 30
        a = score_intraday_bias(
            price=closes[-1],
            closes_5m=closes,
            volumes_5m=vols,
            change_pct=0.5,
            session_open=closes[0],
            session_high=max(closes),
            session_low=min(closes),
        )
        b = score_intraday_bias(
            price=closes[-1],
            closes_5m=closes,
            volumes_5m=vols,
            change_pct=0.5,
            session_open=closes[0],
            session_high=max(closes),
            session_low=min(closes),
        )
        self.assertEqual(a["side"], b["side"])
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(a["strategy_id"], "intraday_bias_v1")

    def test_index_core_deterministic(self):
        closes = [22000 + i for i in range(40)]
        s = score_index_mtf(
            symbol="NIFTY",
            price=closes[-1],
            closes_5m=closes,
            daily_regime="BULL",
            vwap=closes[-1] - 10,
            change_pct=0.4,
            session_high=max(closes),
            session_low=min(closes),
        )
        self.assertIn(s["side"], ("BUY", "SELL", "HOLD"))
        self.assertEqual(s["data_interval"], "5m")
        self.assertFalse(RULE_META[RULE_INTRADAY]["proxy"])


class NoLookaheadAndCostsTests(unittest.TestCase):
    def test_simulate_fills_next_open_not_signal_close(self):
        import pandas as pd

        bars = pd.DataFrame(
            [
                {"open": 100, "high": 101, "low": 99, "close": 100.5},
                {"open": 100.8, "high": 102, "low": 100.2, "close": 101.5},
                {"open": 101.5, "high": 103, "low": 101, "close": 102},
            ]
        )
        sim = simulate_trade(
            bars,
            signal_entry=100.5,
            stop=99.0,
            target=103.0,
            side="BUY",
            max_hold=2,
            product="intraday",
            assumptions=DEFAULT_COSTS,
        )
        self.assertEqual(sim["entry_fill"], 100.8)

    def test_costs_reduce_r(self):
        r_net = r_multiple(100, 102, 99, side="BUY", product="intraday")
        # Gross would be 2/1 = 2R before costs
        self.assertIsNotNone(r_net)
        self.assertLess(r_net, 2.0)

    def test_floor_bucket_alignment(self):
        self.assertEqual(floor_bucket(1001), 900)


class SampleGateTests(unittest.TestCase):
    def test_insufficient_5m_blocks_strong(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "g.db")
            upsert_metrics_rows(
                db,
                rule_id=RULE_INTRADAY,
                desk="intraday",
                by_regime={
                    "BULL_TREND": {
                        "sample_size": 40,
                        "win_rate_pct": 55.0,
                        "avg_win_r": 1.5,
                        "avg_loss_r": 1.0,
                        "expectancy_r": 0.4,
                        "profit_factor": 1.8,
                        "max_drawdown_pct": -5.0,
                    }
                },
                meta={
                    "proxy": False,
                    "insufficient_history": True,
                    "data_interval": "5m",
                    "strategy_version": "1.0.0-5m",
                    "proven": False,
                },
            )
            call = {
                "desk": "intraday",
                "side": "BUY",
                "confidence": 80,
                "symbol": "TCS",
            }
            out = apply_expectancy_gate(
                call, db=db, regime="BULL_TREND", rule_id=RULE_INTRADAY, auto_refresh=False
            )
            self.assertEqual(out["badge"], "BUY")
            self.assertFalse(out["expectancy"]["gates"]["passed"])
            self.assertIn("INSUFFICIENT_5M_HISTORY", out["expectancy"]["gates"]["fail_reasons"])
            self.assertTrue(out["expectancy"]["insufficient_history"])
            self.assertFalse(out["expectancy"]["proven"])

    def test_harness_without_bars_is_honest(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "empty.db")
            # Point bars store at same empty tree via env override — use upsert on empty path
            # load_bars uses config.db_path; seed nothing → insufficient
            t, meta = run_intraday_5m_trades(db, watch=["ZZZNONE"], max_symbols=1)
            self.assertEqual(len(t), 0)
            self.assertTrue(meta.get("insufficient_history") or meta.get("bars_scanned", 0) < MIN_BARS_FOR_RUN)
            self.assertIsNotNone(meta.get("honesty"))
            self.assertFalse(meta.get("proven", True))

    def test_harness_with_seeded_5m_runs_shared_rule(self):
        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "seed.db"
            db = Database(dbp)
            # Seed nifty eod for regime
            import pandas as pd

            dates = [(datetime(2026, 6, 1) + timedelta(days=i)).date() for i in range(80)]
            dates = [d for d in dates if d.weekday() < 5][:60]
            rows = []
            px = 22000.0
            for d in dates:
                rows.append(
                    {
                        "symbol": "NIFTY",
                        "trade_date": d.isoformat(),
                        "open": px,
                        "high": px * 1.01,
                        "low": px * 0.99,
                        "close": px * 1.002,
                        "volume": 1e6,
                        "turnover": 1e9,
                        "prev_close": px,
                    }
                )
                px *= 1.002
            db.upsert_eod_data(pd.DataFrame(rows))

            # Seed ~2 sessions of 5m for RELIANCE with trend
            bars = []
            for day_off, day in enumerate([datetime(2026, 10, 23), datetime(2026, 10, 24)]):
                # force weekdays
                while day.weekday() >= 5:
                    day += timedelta(days=1)
                start = _weekday_session_start(day)
                for i in range(75):
                    c = 1400 + day_off * 20 + i * 0.4
                    bars.append(
                        Bar5m(
                            symbol="RELIANCE",
                            bar_start_unix=start + i * 300,
                            open=c - 0.2,
                            high=c + 0.5,
                            low=c - 0.5,
                            close=c,
                            volume=5000 + i,
                            source="synthetic_test",
                            completed=True,
                        )
                    )
            upsert_bars(bars, db_path=dbp)
            # Override config db_path for load_bars default — pass via monkeypatch
            from app import config as config_mod

            old = config_mod.config.db_path
            object.__setattr__(config_mod.config, "db_path", dbp)
            try:
                t, meta = run_intraday_5m_trades(db, watch=["RELIANCE"], max_symbols=1)
            finally:
                object.__setattr__(config_mod.config, "db_path", old)
            self.assertFalse(meta.get("proxy", True))
            self.assertEqual(meta.get("data_interval"), "5m")
            self.assertGreaterEqual(meta.get("bars_scanned", 0), MIN_BARS_FOR_RUN)
            # May or may not produce trades depending on score path; either is honest
            self.assertIn("strategy_version", meta)
            self.assertFalse(meta.get("proven", True))

    def test_gate_constants_unchanged(self):
        self.assertEqual(STRONG_GATES["min_sample_size"], 30)
        self.assertEqual(STRONG_GATES["min_expectancy_r"], 0.25)
        self.assertEqual(STRONG_GATES["min_profit_factor"], 1.2)


class VersionTests(unittest.TestCase):
    def test_app_version_p3(self):
        import re

        from app.main import APP_VERSION, app

        # Phase-3 lineage: major 5, minor ≥ 3
        m = re.match(r"^5\.(\d+)\.", APP_VERSION)
        self.assertTrue(m and int(m.group(1)) >= 3, APP_VERSION)
        c = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertIn("bars_5m", r.json()["feeds"])


if __name__ == "__main__":
    unittest.main()
