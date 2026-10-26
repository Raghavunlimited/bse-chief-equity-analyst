#!/usr/bin/env python3
"""Phase 1: demo platform seed is DISABLED.

Previously created demo users + synthetic signals. That path is forbidden.
Use Kotak Force full for EOD and live desks for LTP.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "REFUSED: seed_platform.py demo users/signals were removed in Phase 1.\n"
        "This personal desk does not boot with synthetic data.\n"
        "Set KOTAK_CONSUMER_KEY, MARKET_DATA_ADAPTER=live, AUTH_ENABLED=false,\n"
        "then run uvicorn and Force full for real EOD.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
