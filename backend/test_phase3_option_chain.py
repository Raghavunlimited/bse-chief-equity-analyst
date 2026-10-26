"""Phase 3 — Greeks, OI buildup, PCR/Max Pain, chain wiring (offline + public scrip)."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.kotak.greeks import compute_greeks, implied_vol, price_bs, select_model  # noqa: E402
from app.kotak.oi_buildup import classify_oi_buildup, max_pain_strike  # noqa: E402
from app.kotak.option_chain import apply_chain_to_signal, pick_expiry  # noqa: E402
from app.kotak.scrip_master import ScripMaster  # noqa: E402


class TestGreeks(unittest.TestCase):
    def test_model_selection(self):
        self.assertEqual(select_model("NIFTY"), "black76")
        self.assertEqual(select_model("RELIANCE"), "black_scholes")

    def test_bs_call_put_and_iv_roundtrip(self):
        spot, k, t, r, q, sigma = 100.0, 100.0, 30 / 365.25, 0.065, 0.0, 0.20
        call = price_bs(spot, k, t, r, q, sigma, "CE")
        put = price_bs(spot, k, t, r, q, sigma, "PE")
        self.assertGreater(call, 0)
        self.assertGreater(put, 0)
        # Put-call parity (q=0): C - P ≈ S - K e^{-rT}
        lhs = call - put
        rhs = spot - k * __import__("math").exp(-r * t)
        self.assertAlmostEqual(lhs, rhs, places=4)
        iv = implied_vol(
            premium=call, spot=spot, strike=k, t_years=t, right="CE", r=r, q=q, model="black_scholes"
        )
        self.assertIsNotNone(iv)
        self.assertAlmostEqual(iv, sigma, places=3)

    def test_greeks_nifty_black76(self):
        g = compute_greeks(
            premium=120.0,
            spot=24500.0,
            strike=24500.0,
            t_years=7 / 365.25,
            right="CE",
            underlying="NIFTY",
        )
        self.assertTrue(g.ok)
        self.assertEqual(g.model, "black76")
        self.assertIsNotNone(g.iv)
        self.assertGreater(g.delta or 0, 0)
        self.assertGreater(g.vega or 0, 0)


class TestOiBuildup(unittest.TestCase):
    def test_four_quadrants(self):
        self.assertEqual(classify_oi_buildup(1.0, 100).label, "Long Buildup")
        self.assertEqual(classify_oi_buildup(-1.0, 100).label, "Short Buildup")
        self.assertEqual(classify_oi_buildup(1.0, -100).label, "Short Covering")
        self.assertEqual(classify_oi_buildup(-1.0, -100).label, "Long Unwinding")
        self.assertEqual(classify_oi_buildup(0.0, 10).label, "Neutral")
        self.assertEqual(classify_oi_buildup(None, 10).label, "Unknown")

    def test_max_pain(self):
        strikes = [100.0, 110.0, 120.0]
        call_oi = {100.0: 10, 110.0: 50, 120.0: 5}
        put_oi = {100.0: 5, 110.0: 40, 120.0: 60}
        mp = max_pain_strike(strikes, call_oi, put_oi)
        self.assertIn(mp, strikes)
        # Brute verify minimizer
        def pain(p):
            return sum(
                call_oi[k] * max(p - k, 0) + put_oi[k] * max(k - p, 0) for k in strikes
            )

        self.assertEqual(mp, min(strikes, key=pain))


class TestChainRules(unittest.TestCase):
    def test_apply_pcr_and_walls(self):
        sig = {
            "symbol": "NIFTY",
            "side": "BUY",
            "score": 70.0,
            "confidence": 65.0,
            "thesis": "NIFTY: BUY bias",
            "tags": ["EMA_BULL"],
            "price": 24500.0,
        }
        chain = {
            "expiry": "2026-10-27",
            "spot": 24500.0,
            "atm": 24500.0,
            "analytics": {
                "total_oi_pcr": 1.35,
                "atm_pcr": 1.1,
                "volume_pcr": 0.9,
                "max_pain": 24400.0,
                "call_wall": 24550.0,  # ~0.2% above → near wall
                "put_wall": 24000.0,
                "atm_straddle_premium": 250.0,
                "pcr_regime": "PUT_HEAVY",
                "spot_to_call_wall_pct": 0.2,
                "spot_to_put_wall_pct": 2.0,
            },
            "future": {"buildup": {"label": "Long Buildup"}},
        }
        out = apply_chain_to_signal(sig, chain)
        self.assertTrue(out["option_chain"]["available"])
        self.assertIn("PCR_PUT_HEAVY", out["tags"])
        self.assertIn("NEAR_CALL_WALL", out["tags"])
        # Near call wall should cut BUY conviction (possibly HOLD)
        self.assertLessEqual(out["confidence"], 65.0)


class TestExpiryPick(unittest.TestCase):
    def test_pick_nearest_and_monthly(self):
        sm = ScripMaster(cache_dir=ROOT / "data" / "kotak_cache")
        try:
            sm.ensure_loaded()
            near = pick_expiry("NIFTY", mode="nearest", scrip=sm)
            month = pick_expiry("NIFTY", mode="monthly", scrip=sm)
        except RuntimeError as e:
            self.skipTest(str(e))
        today = date.today()
        self.assertGreaterEqual(near, today)
        self.assertGreaterEqual(month, near)
        # monthly should be last expiry in its calendar month among upcoming
        exps = [date.fromisoformat(e) for e in sm.list_expiries("NIFTY", kind="OPT")]
        upcoming = [e for e in exps if e >= today]
        same_m = [e for e in upcoming if (e.year, e.month) == (month.year, month.month)]
        self.assertEqual(month, same_m[-1])


class TestAppRoutes(unittest.TestCase):
    def test_option_chain_routes_mounted(self):
        from app.main import APP_VERSION, app

        self.assertTrue(
            APP_VERSION.startswith("4.") or APP_VERSION.startswith("5."),
            APP_VERSION,
        )
        paths = {getattr(r, "path", None) for r in app.routes}
        self.assertIn("/api/kotak/option-chain/status", paths)
        self.assertIn("/api/kotak/option-chain/activate", paths)
        self.assertIn("/api/kotak/option-chain/{underlying}", paths)
        self.assertIn("/api/kotak/option-chain/{underlying}/expiries", paths)


if __name__ == "__main__":
    unittest.main()
