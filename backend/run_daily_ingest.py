#!/usr/bin/env python3
"""CLI: incremental NSE ingest + NIFTY + indicators."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.pipeline import run_incremental_ingest


def main():
    result = run_incremental_ingest()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
