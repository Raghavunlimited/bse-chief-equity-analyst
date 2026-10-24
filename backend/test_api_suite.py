#!/usr/bin/env python3
"""Smoke tests against a running API (http://localhost:8000)."""
from __future__ import annotations

import sys

import requests

BASE = "http://localhost:8000"


def check(name: str, method: str, path: str, **kwargs) -> bool:
    url = f"{BASE}{path}"
    try:
        r = requests.request(method, url, timeout=120, **kwargs)
        ok = r.status_code == 200
        print(f"{'OK' if ok else 'FAIL'} {name} [{r.status_code}]")
        if ok and path.endswith("/weekly-picks"):
            data = r.json()
            print(f"     status={data.get('status')} picks={len(data.get('candidates', []))}")
        if ok and "backtest" in path:
            stats = r.json().get("stats", {})
            print(f"     weeks={stats.get('weeks')} trades={stats.get('trades')} wr={stats.get('win_rate')}")
        return ok
    except Exception as e:
        print(f"FAIL {name}: {e}")
        return False


def main():
    tests = [
        ("health", "GET", "/api/health"),
        ("stats", "GET", "/api/stats"),
        ("regime", "GET", "/api/market-regime"),
        ("picks", "GET", "/api/weekly-picks"),
    ]
    results = [check(*t) for t in tests]
    # backtest only if we have enough data
    results.append(check("backtest", "POST", "/api/backtest", json={}))
    return 0 if all(results[:4]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
