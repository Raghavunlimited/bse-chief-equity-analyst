#!/usr/bin/env python3
"""MVP platform tests: auth/RBAC, append-only signals, LLM vault secrecy, demo provenance."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Isolate DB + secrets before app import
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ["DATABASE_PATH"] = _TMP.name
os.environ["AUTH_ENABLED"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-32chars-minimum!!"
os.environ["ALLOW_DEMO_DATA"] = "true"
os.environ["MARKET_DATA_ADAPTER"] = "demo"
os.environ["LLM_FERNET_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.platform_db import PlatformDB  # noqa: E402
from app.auth_deps import hash_password  # noqa: E402
from app.config import config  # noqa: E402


class MvpPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.db_path = Path(_TMP.name)
        config.auth_enabled = True
        db = PlatformDB(config.db_path)
        db.create_user(
            "admin@test.local",
            hash_password("AdminPass1!"),
            role="admin",
            display_name="Admin",
        )
        db.create_user(
            "cust@test.local",
            hash_password("CustPass1!"),
            role="customer",
            display_name="Customer",
        )
        cls.client = TestClient(app)

    def _login(self, email: str, password: str) -> str:
        r = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

    def test_auth_me_and_customer_blocked_from_admin(self):
        token = self._login("cust@test.local", "CustPass1!")
        headers = {"X-Session-Token": token}
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "customer")
        denied = self.client.get("/api/admin/instruments", headers=headers)
        self.assertEqual(denied.status_code, 403)

    def test_admin_publish_and_revise_append_only(self):
        token = self._login("admin@test.local", "AdminPass1!")
        headers = {"X-Session-Token": token}
        pub = self.client.post(
            "/api/admin/signals",
            headers=headers,
            json={
                "symbol": "RELIANCE",
                "category": "swing",
                "direction": "buy",
                "timeframe": "1w",
                "rationale": "Demo publish for audit test",
                "data_mode": "demo",
                "expires_in_hours": 48,
            },
        )
        self.assertEqual(pub.status_code, 200, pub.text)
        sid = pub.json()["id"]
        rev = self.client.post(
            f"/api/admin/signals/{sid}/revise",
            headers=headers,
            json={"direction": "none", "rationale": "Revised — insufficient follow-through"},
        )
        self.assertEqual(rev.status_code, 200, rev.text)
        self.assertEqual(rev.json()["supersedes_id"], sid)
        self.assertGreaterEqual(rev.json()["revision"], 2)
        # Prior row retained as revised
        hist = self.client.get(
            "/api/platform/signals",
            headers=headers,
            params={"history": True, "symbol": "RELIANCE"},
        )
        self.assertEqual(hist.status_code, 200)
        ids = {s["id"] for s in hist.json()["signals"]}
        self.assertIn(sid, ids)
        prior = next(s for s in hist.json()["signals"] if s["id"] == sid)
        self.assertEqual(prior["status"], "revised")

    def test_llm_vault_never_returns_key(self):
        token = self._login("cust@test.local", "CustPass1!")
        headers = {"X-Session-Token": token}
        put = self.client.put(
            "/api/me/llm",
            headers=headers,
            json={
                "provider": "openai",
                "api_key": "sk-test-secret-key-never-echo",
                "model": "gpt-4o",
            },
        )
        self.assertEqual(put.status_code, 200, put.text)
        self.assertTrue(put.json()["configured"])
        self.assertNotIn("api_key", put.json())
        get = self.client.get("/api/me/llm", headers=headers)
        self.assertEqual(get.status_code, 200)
        body = get.json()
        self.assertTrue(body["configured"])
        self.assertIsNone(body.get("api_key"))
        dumped = str(body)
        self.assertNotIn("sk-test-secret-key-never-echo", dumped)
        # Delete
        delete = self.client.delete("/api/me/llm", headers=headers)
        self.assertEqual(delete.status_code, 200)
        get2 = self.client.get("/api/me/llm", headers=headers)
        self.assertFalse(get2.json()["configured"])

    def test_demo_signals_labeled(self):
        token = self._login("cust@test.local", "CustPass1!")
        headers = {"X-Session-Token": token}
        # seed one demo signal as admin
        at = self._login("admin@test.local", "AdminPass1!")
        self.client.post(
            "/api/admin/signals",
            headers={"X-Session-Token": at},
            json={
                "symbol": "GOLD",
                "category": "commodity",
                "direction": "none",
                "timeframe": "1d",
                "rationale": "Insufficient commodity evidence in test",
                "data_mode": "demo",
            },
        )
        r = self.client.get("/api/platform/demo/signals", headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data_mode"], "demo")
        self.assertIn("DEMO", r.json()["label"])

    def test_market_quote_demo_provenance(self):
        from app import auth_deps

        auth_deps._buckets.clear()
        token = self._login("cust@test.local", "CustPass1!")
        r = self.client.get(
            "/api/platform/market/RELIANCE/quote",
            headers={"X-Session-Token": token},
            params={"category": "swing"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["provenance"]["data_mode"], "demo")

    def test_login_rate_limit_soft(self):
        from app import auth_deps

        auth_deps._buckets.clear()
        codes = []
        for i in range(20):
            r = self.client.post(
                "/api/auth/login",
                json={"email": "nosuch@test.local", "password": f"bad{i}"},
            )
            codes.append(r.status_code)
        self.assertTrue(
            any(c in (401, 429) for c in codes),
            f"expected 401/429, got {set(codes)}",
        )
        self.assertTrue(429 in codes or codes.count(401) >= 10)
        auth_deps._buckets.clear()

    def test_methodology_withholds_when_thin(self):
        from app.signals.methodology import score_evidence

        thin = score_evidence({"rsi_14": 50})
        self.assertEqual(thin["direction"], "none")
        self.assertTrue(thin["insufficient"])

    def test_llm_vault_is_per_user(self):
        """Customer A cannot read Customer B's vault metadata as if shared."""
        from app import auth_deps

        auth_deps._buckets.clear()
        # Register a second customer
        email_b = "custb@test.local"
        db = PlatformDB(config.db_path)
        if not db.get_user_by_email(email_b):
            db.create_user(email_b, hash_password("CustBPass1!"), role="customer")
        token_a = self._login("cust@test.local", "CustPass1!")
        token_b = self._login(email_b, "CustBPass1!")
        ha = {"X-Session-Token": token_a}
        hb = {"X-Session-Token": token_b}
        put = self.client.put(
            "/api/me/llm",
            headers=ha,
            json={
                "provider": "anthropic",
                "api_key": "sk-ant-user-a-secret-key-xx",
                "model": "claude-opus-4-20250514",
            },
        )
        self.assertEqual(put.status_code, 200, put.text)
        meta_a = self.client.get("/api/me/llm", headers=ha).json()
        meta_b = self.client.get("/api/me/llm", headers=hb).json()
        self.assertTrue(meta_a["configured"])
        self.assertEqual(meta_a["provider"], "anthropic")
        self.assertFalse(meta_b["configured"])
        self.assertIsNone(meta_b.get("api_key"))
        # B must not see A's key material anywhere
        self.assertNotIn("sk-ant-user-a", str(meta_b))


if __name__ == "__main__":
    unittest.main()
