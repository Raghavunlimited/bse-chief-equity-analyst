#!/usr/bin/env python3
"""Phase 1: synthetic EOD seed is DISABLED — never write demo prices into the DB."""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "REFUSED: seed_demo_data.py is forbidden after Phase 1.\n"
        "Synthetic EOD would reintroduce DEMO provenance. Use Kotak Force full instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
