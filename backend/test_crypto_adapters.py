#!/usr/bin/env python3
"""Crypto vault helpers + demo market adapter — offline unit tests."""
from __future__ import annotations

import os
import unittest

# Stable key before importing crypto (lru_cache)
os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-32chars-min!")
os.environ["LLM_FERNET_KEY"] = ""

from app.adapters.demo import DemoAdapter, DEMO_SYMBOLS  # noqa: E402
from app.crypto_secrets import decrypt_secret, encrypt_secret, redact  # noqa: E402


class CryptoSecretsTests(unittest.TestCase):
    def test_roundtrip(self):
        plain = "sk-test-secret-value-abcdef"
        cipher = encrypt_secret(plain)
        self.assertNotEqual(cipher, plain)
        self.assertEqual(decrypt_secret(cipher), plain)

    def test_tampered_ciphertext_raises(self):
        cipher = encrypt_secret("hello-world-key")
        with self.assertRaises(ValueError):
            decrypt_secret(cipher[:-4] + "xxxx")

    def test_redact(self):
        self.assertEqual(redact(""), "")
        self.assertEqual(redact("abcd"), "***")
        self.assertTrue(redact("abcdefgh").startswith("abcd"))
        self.assertIn("***", redact("abcdefgh"))


class DemoAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = DemoAdapter()

    def test_quote_provenance_demo(self):
        q = self.adapter.get_quote("RELIANCE")
        self.assertEqual(q["provenance"], "demo")
        self.assertEqual(q["source"], "demo")
        self.assertIsNotNone(q["last"])
        self.assertEqual(q["symbol"], "RELIANCE")

    def test_unknown_symbol_raises(self):
        with self.assertRaises(KeyError):
            self.adapter.get_quote("NOTAREAL")

    def test_bars_deterministic_length(self):
        a = self.adapter.get_bars("TCS", lookback=10)
        b = self.adapter.get_bars("TCS", lookback=10)
        self.assertEqual(len(a["bars"]), 10)
        self.assertEqual(a["bars"], b["bars"])
        self.assertEqual(a["provenance"], "demo")

    def test_equity_oi_zero_vs_commodity_positive(self):
        eq = self.adapter.get_oi("INFY")
        self.assertEqual(eq["open_interest"], 0.0)
        cmd = self.adapter.get_oi("GOLD")
        self.assertGreater(cmd["open_interest"], 0)

    def test_commodity_financials_null(self):
        f = self.adapter.get_financials("CRUDE")
        self.assertIsNone(f["pe"])
        self.assertEqual(f["extras"]["asset_class"], "commodity")
        self.assertEqual(f["provenance"], "demo")

    def test_universe_matches_seed(self):
        self.assertEqual(set(self.adapter.list_symbols()), set(DEMO_SYMBOLS))


if __name__ == "__main__":
    unittest.main()
