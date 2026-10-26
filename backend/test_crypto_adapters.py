"""Phase 1: vault helpers + live adapter registry (demo forbidden)."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-32chars-min!!")
os.environ["MARKET_DATA_ADAPTER"] = "live"
os.environ["AUTH_ENABLED"] = "false"

from app.adapters.registry import (  # noqa: E402
    DemoAdapterForbidden,
    clear_adapter_cache,
    get_market_adapter,
)
from app.adapters.live_yahoo import LiveYahooAdapter  # noqa: E402
from app.crypto_secrets import encrypt_secret, decrypt_secret  # noqa: E402
from app import config as config_mod  # noqa: E402


class VaultTests(unittest.TestCase):
    def test_roundtrip(self):
        token = encrypt_secret("sk-test-secret-value")
        self.assertNotEqual(token, "sk-test-secret-value")
        self.assertEqual(decrypt_secret(token), "sk-test-secret-value")


class RegistryTests(unittest.TestCase):
    def tearDown(self):
        config_mod.config.market_data_adapter = "live"
        clear_adapter_cache()

    def test_live_adapter(self):
        clear_adapter_cache()
        config_mod.config.market_data_adapter = "live"
        adapter = get_market_adapter()
        self.assertIsInstance(adapter, LiveYahooAdapter)
        # Phase 2: facade resolves Kotak WS then optional Yahoo FALLBACK
        self.assertEqual(adapter.source_id, "live_quote_provider")

    def test_demo_forbidden(self):
        clear_adapter_cache()
        config_mod.config.market_data_adapter = "demo"
        with self.assertRaises(DemoAdapterForbidden):
            get_market_adapter()

    def test_demo_module_import_fails(self):
        with self.assertRaises(RuntimeError):
            import importlib

            importlib.import_module("app.adapters.demo")


if __name__ == "__main__":
    unittest.main()
