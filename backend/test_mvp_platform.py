"""Phase 1 platform smoke: auth-off personal desk + demo endpoints gone."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ["AUTH_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "ci-test-secret-key-32chars-min!!"
os.environ["MARKET_DATA_ADAPTER"] = "live"

# Isolate DB
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_PATH"] = _tmp.name

from fastapi.testclient import TestClient  # noqa: E402

from app import config as config_mod  # noqa: E402
from app.adapters.registry import clear_adapter_cache  # noqa: E402
from app.main import app  # noqa: E402
from app.platform_db import PlatformDB  # noqa: E402


class Phase1PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_mod.config.auth_enabled = False
        config_mod.config.market_data_adapter = "live"
        config_mod.config.allow_demo_data = False
        clear_adapter_cache()
        PlatformDB(Path(_tmp.name))
        cls.client = TestClient(app)

    def test_health_no_demo(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["feeds"]["demo_allowed"])
        self.assertEqual(body["feeds"]["market_data_adapter"], "live")
        self.assertIn("session", body)

    def test_market_session(self):
        r = self.client.get("/api/market/session")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("session_label", body)
        self.assertIn("stale_sec_threshold", body)
        self.assertIn("badge", body)

    def test_demo_signals_gone(self):
        r = self.client.get("/api/platform/demo/signals")
        self.assertEqual(r.status_code, 410)

    def test_auth_status_personal(self):
        r = self.client.get("/api/auth/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["auth_enabled"])


if __name__ == "__main__":
    unittest.main()
