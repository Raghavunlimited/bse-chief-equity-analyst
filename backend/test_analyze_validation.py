#!/usr/bin/env python3
"""Unit tests for POST /api/analyze validation — no live LLM calls."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

backend = Path(__file__).resolve().parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from fastapi.testclient import TestClient

from app.config import config
from app.llm_analyze import LlmAnalyzeError
from app.main import app

client = TestClient(app)


class AnalyzeValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prev_auth = config.auth_enabled
        config.auth_enabled = False  # exercise validation without session gate

    @classmethod
    def tearDownClass(cls):
        config.auth_enabled = cls._prev_auth

    def test_missing_signal_422(self):
        r = client.post(
            "/api/analyze",
            json={"provider": "openai", "api_key": "sk-fake-key-12345"},
        )
        self.assertEqual(r.status_code, 422)

    def test_empty_signal_422(self):
        r = client.post(
            "/api/analyze",
            json={
                "provider": "openai",
                "api_key": "sk-fake-key-12345",
                "signal": {},
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_short_api_key_422(self):
        r = client.post(
            "/api/analyze",
            json={
                "provider": "openai",
                "api_key": "short",
                "signal": {"symbol": "RELIANCE", "side": "BUY"},
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_missing_api_key_422(self):
        r = client.post(
            "/api/analyze",
            json={
                "provider": "openai",
                "signal": {"symbol": "RELIANCE", "side": "BUY"},
                "use_stored_key": False,
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_invalid_provider_422(self):
        r = client.post(
            "/api/analyze",
            json={
                "provider": "grok",
                "api_key": "sk-fake-key-12345",
                "signal": {"symbol": "RELIANCE"},
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_signal_too_large_422(self):
        big = {"blob": "x" * 40_000}
        r = client.post(
            "/api/analyze",
            json={
                "provider": "openai",
                "api_key": "sk-fake-key-12345",
                "signal": big,
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_context_too_large_422(self):
        r = client.post(
            "/api/analyze",
            json={
                "provider": "openai",
                "api_key": "sk-fake-key-12345",
                "signal": {"symbol": "TCS"},
                "context": {"notes": "y" * 40_000},
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_body_api_key_accepted_mocked(self):
        fake = {
            "summary": "ok",
            "bull_case": "b",
            "bear_case": "c",
            "risks": "r",
            "checklist": ["check"],
            "provider": "openai",
            "model": "gpt-4o-mini",
        }
        with patch("app.routers.analyze.analyze_signal", return_value=fake) as mock_fn:
            r = client.post(
                "/api/analyze",
                json={
                    "provider": "openai",
                    "api_key": "sk-from-body-abcdef12",
                    "signal": {"symbol": "INFY", "side": "HOLD"},
                },
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body.get("ai_generated"))
        self.assertIn("disclaimer", body)
        self.assertEqual(body["analysis"]["summary"], "ok")
        self.assertNotIn("api_key", body)
        mock_fn.assert_called_once()
        args, kwargs = mock_fn.call_args
        self.assertEqual(args[2], "sk-from-body-abcdef12")

    def test_llm_auth_error_mapped_401(self):
        with patch(
            "app.routers.analyze.analyze_signal",
            side_effect=LlmAnalyzeError(
                "LLM authentication failed — check your API key",
                status_code=401,
            ),
        ):
            r = client.post(
                "/api/analyze",
                json={
                    "provider": "openai",
                    "api_key": "sk-fake-but-long-enough",
                    "signal": {"symbol": "RELIANCE", "side": "BUY"},
                },
            )
        self.assertEqual(r.status_code, 401)
        self.assertIn("authentication", r.json()["detail"].lower())
        self.assertNotIn("sk-fake", r.text)


if __name__ == "__main__":
    unittest.main()
