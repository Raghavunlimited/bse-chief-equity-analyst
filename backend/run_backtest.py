#!/usr/bin/env python3
"""CLI wrapper around the shared weekly backtest."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.store import Database
from app.strategy.backtest import run_weekly_backtest
from universe import SECTOR_MAP


def main():
    db = Database(config.db_path)
    result = run_weekly_backtest(db, sector_map=SECTOR_MAP)
    # Compact print for CLI
    out = {
        "status": result.get("status"),
        "message": result.get("message"),
        "stats": result.get("stats"),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
