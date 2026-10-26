"""Phase 7 — local-only posture, CORS, secrets redaction, schema, CI honesty."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ.setdefault("BIND_HOST", "127.0.0.1")
os.environ.setdefault("ALLOW_PUBLIC_BIND", "false")
os.environ.setdefault("EOD_INGEST_SCHEDULE_ENABLED", "false")

from app.config import Config  # noqa: E402
from app.kotak.tick_guard import sanitize_error_text  # noqa: E402
from app.ops_security import (  # noqa: E402
    assert_safe_boot,
    check_sqlite_schema,
    is_loopback_host,
    is_public_bind_host,
    secret_key_is_default,
    security_posture,
)


class BindAndCorsTests(unittest.TestCase):
    def test_loopback_detection(self):
        self.assertTrue(is_loopback_host("127.0.0.1"))
        self.assertTrue(is_loopback_host("localhost"))
        self.assertTrue(is_public_bind_host("0.0.0.0"))
        self.assertFalse(is_public_bind_host("127.0.0.1"))

    def test_cors_never_star_by_default(self):
        c = Config()
        origins = c.cors_origin_list()
        self.assertNotIn("*", origins)
        self.assertTrue(any("localhost:3000" in o for o in origins))

    def test_cors_explicit_star_allowed_when_set(self):
        c = Config(cors_origins="*")
        self.assertEqual(c.cors_origin_list(), ["*"])

    def test_boot_refuses_public_bind_auth_off(self):
        from app import config as cfg_mod
        from app import ops_security as ops

        old_bind = cfg_mod.config.bind_host
        old_auth = cfg_mod.config.auth_enabled
        old_allow = cfg_mod.config.allow_public_bind
        try:
            object.__setattr__(cfg_mod.config, "bind_host", "0.0.0.0")
            object.__setattr__(cfg_mod.config, "auth_enabled", False)
            object.__setattr__(cfg_mod.config, "allow_public_bind", False)
            with self.assertRaises(RuntimeError) as ctx:
                ops.assert_safe_boot()
            self.assertIn("ALLOW_PUBLIC_BIND", str(ctx.exception))
        finally:
            object.__setattr__(cfg_mod.config, "bind_host", old_bind)
            object.__setattr__(cfg_mod.config, "auth_enabled", old_auth)
            object.__setattr__(cfg_mod.config, "allow_public_bind", old_allow)

    def test_boot_ok_loopback(self):
        from app import config as cfg_mod

        object.__setattr__(cfg_mod.config, "bind_host", "127.0.0.1")
        object.__setattr__(cfg_mod.config, "allow_public_bind", False)
        assert_safe_boot()  # should not raise


class SanitizeTests(unittest.TestCase):
    def test_redacts_consumer_key_and_token(self):
        raw = "failed consumer_key=abcSECRET123XYZ token=Bearer.deadbeef mpin=1234"
        out = sanitize_error_text(raw)
        self.assertNotIn("abcSECRET123XYZ", out)
        self.assertNotIn("deadbeef", out)
        self.assertNotIn("1234", out)
        self.assertIn("[REDACTED]", out)

    def test_uuid_redacted(self):
        out = sanitize_error_text("sid=550e8400-e29b-41d4-a716-446655440000")
        self.assertIn("[REDACTED]", out)


class SchemaAndHealthTests(unittest.TestCase):
    def test_schema_check_on_temp_db(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.db"
            result = check_sqlite_schema(path)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["engine"], "sqlite")
            self.assertEqual(result["missing_tables"], [])
            self.assertIn("eod", result["present_tables"])
            self.assertIn("bars_5m", result["present_tables"])
            self.assertIn("ingest_runs", result["present_tables"])
            # Never leak absolute paths with home dirs ideally — basename only
            self.assertEqual(result["db_path_basename"], "t.db")

    def test_security_posture_not_production_claim(self):
        from app import config as config_module

        p = security_posture()
        self.assertFalse(p["production_ready_claim"])
        self.assertEqual(p["deployment_model"], "personal_local_research_desk")
        self.assertIn("auth_enabled", p)
        self.assertNotIn("secret_key", p)
        # Inventory may mention the name API_KEY / api_key_gate — never the secret value
        blob = str(p)
        configured_key = (config_module.config.api_key or "").strip()
        if configured_key:
            self.assertNotIn(configured_key, blob)
        self.assertIn("api_key_gate", p)
        self.assertIsInstance(p["api_key_gate"], dict)
        self.assertNotIn("value", p["api_key_gate"])
        self.assertIn("inventory", p["api_key_gate"])
        inv = p["api_key_gate"]["inventory"]
        self.assertIn("/api/strategy-evaluation/evaluate", inv.get("post_paths") or [])

    def test_health_endpoints(self):
        from fastapi.testclient import TestClient

        from app.main import APP_VERSION, app

        self.assertTrue(
            APP_VERSION.startswith("5.7")
            or APP_VERSION.startswith("5.8")
            or APP_VERSION.startswith("5.9")
            or APP_VERSION.startswith("5.10")
            or APP_VERSION.startswith("5.11")
            or APP_VERSION.startswith("5.12")
            or "upgrade-p7" in APP_VERSION
            or "options-oi" in APP_VERSION
            or "trade-journal" in APP_VERSION
            or "position-sizing" in APP_VERSION
            or "market-events" in APP_VERSION
            or "strategy-eval" in APP_VERSION,
            APP_VERSION,
        )
        c = TestClient(app)
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("liveness"))
        self.assertIn("security", body)
        self.assertFalse(body["security"]["production_ready_claim"])
        self.assertIn("schema", body)
        self.assertNotIn("KOTAK_CONSUMER_KEY", str(body))
        # ready may be 503 without fresh EOD — still must be secret-safe
        r2 = c.get("/api/health/ready")
        self.assertIn(r2.status_code, (200, 503))
        ready = r2.json()
        self.assertIn("data_ready", ready)
        self.assertNotIn("consumer_key_value", str(ready))

    def test_root_declares_not_production(self):
        from fastapi.testclient import TestClient

        from app.main import app

        c = TestClient(app)
        root = c.get("/").json()
        self.assertFalse(root.get("production_ready_claim", True))


class DefaultSecretFlagTests(unittest.TestCase):
    def test_ci_secret_not_example_default(self):
        # CI / this suite uses a non-example SECRET_KEY
        self.assertFalse(secret_key_is_default())


if __name__ == "__main__":
    unittest.main()
