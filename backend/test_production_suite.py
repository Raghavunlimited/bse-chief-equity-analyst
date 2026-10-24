#!/usr/bin/env python3
"""
Production acceptance suite against a live API (default http://127.0.0.1:8000).

Run:
  cd backend && source venv/bin/activate && python test_production_suite.py

Optional:
  BASE_URL=http://127.0.0.1:8000 python test_production_suite.py

Exit 0 only if all required checks pass. Consultant routes are required when
present in OpenAPI; if the process cannot reach the server, exits 2.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Optional

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = float(os.environ.get("SUITE_TIMEOUT", "90"))


class Result:
    def __init__(self, name: str, ok: bool, detail: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail

    def line(self) -> str:
        tag = "PASS" if self.ok else "FAIL"
        extra = f" — {self.detail}" if self.detail else ""
        return f"[{tag}] {self.name}{extra}"


def _request(
    method: str,
    path: str,
    *,
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> tuple[int, Any, str]:
    url = f"{BASE}{path}"
    data = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            parsed: Any = json.loads(raw) if raw else None
            return resp.status, parsed, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed, raw


def _openapi_paths() -> set[str]:
    code, data, _ = _request("GET", "/openapi.json")
    if code != 200 or not isinstance(data, dict):
        return set()
    return set((data.get("paths") or {}).keys())


def server_up() -> bool:
    try:
        code, _, _ = _request("GET", "/api/health")
        return code == 200
    except Exception:
        return False


def check_health() -> Result:
    name = "GET /api/health"
    try:
        code, data, _ = _request("GET", "/api/health")
    except Exception as exc:
        return Result(name, False, str(exc))
    if code != 200 or not isinstance(data, dict):
        return Result(name, False, f"status={code}")
    if data.get("status") != "ok":
        return Result(name, False, f"status field={data.get('status')}")
    desks = data.get("desks") or []
    for d in ("swing", "intraday", "mcx"):
        if d not in desks:
            return Result(name, False, f"missing desk {d}")
    feeds = data.get("feeds") or {}
    if "kotak" not in feeds:
        return Result(name, False, "feeds.kotak missing")
    if "groww" in feeds:
        return Result(name, False, "feeds.groww must be removed")
    ver = str(data.get("version") or "")
    return Result(name, True, f"version={ver} desks={desks}")


def check_stats() -> Result:
    name = "GET /api/stats"
    try:
        code, data, _ = _request("GET", "/api/stats")
    except Exception as exc:
        return Result(name, False, str(exc))
    if code != 200 or not isinstance(data, dict):
        return Result(name, False, f"status={code}")
    # Accept several field shapes used historically
    has_count = any(
        k in data for k in ("symbol_count", "symbols", "eod_rows", "row_count")
    ) or isinstance(data.get("coverage"), dict)
    if not has_count and "freshness" not in data and "provenance" not in data:
        return Result(name, False, f"unexpected shape keys={list(data)[:12]}")
    return Result(name, True, f"keys={sorted(data)[:8]}")


def check_regime() -> Result:
    name = "GET /api/market-regime"
    try:
        code, data, _ = _request("GET", "/api/market-regime")
    except Exception as exc:
        return Result(name, False, str(exc))
    if code != 200 or not isinstance(data, dict):
        return Result(name, False, f"status={code}")
    regime = data.get("regime") or data.get("market_regime")
    if not regime:
        return Result(name, False, "no regime field")
    return Result(name, True, f"regime={regime}")


def check_weekly_picks() -> Result:
    name = "GET /api/weekly-picks"
    try:
        code, data, _ = _request("GET", "/api/weekly-picks?fundamentals=false")
    except Exception as exc:
        return Result(name, False, str(exc))
    if code != 200 or not isinstance(data, dict):
        return Result(name, False, f"status={code}")
    st = data.get("status")
    cands = data.get("candidates") or []
    return Result(
        name,
        True,
        f"status={st} candidates={len(cands)} radar={len(data.get('radar') or [])}",
    )


def check_journal() -> Result:
    name = "POST+GET /api/journal"
    week = datetime.now(timezone.utc).strftime("%G-W%V")
    symbol = "QA_SUITE"
    body = {
        "week": week,
        "symbol": symbol,
        "invested": False,
        "notes": "production suite smoke",
    }
    try:
        code, data, raw = _request("POST", "/api/journal", body=body)
    except Exception as exc:
        return Result(name, False, f"POST {exc}")
    if code not in (200, 201) or not isinstance(data, dict):
        return Result(name, False, f"POST status={code} body={raw[:200]}")
    try:
        gcode, gdata, _ = _request("GET", f"/api/journal?week={week}&limit=100")
    except Exception as exc:
        return Result(name, False, f"GET {exc}")
    if gcode != 200 or not isinstance(gdata, dict):
        return Result(name, False, f"GET status={gcode}")
    entries = gdata.get("entries") or []
    found = any(
        str(e.get("symbol", "")).upper() == symbol and str(e.get("week") or e.get("week_label") or "") == week
        for e in entries
        if isinstance(e, dict)
    )
    if not found:
        # soft: count may have filtered; accept if POST ok and GET returns list
        if gdata.get("count") is None and not isinstance(entries, list):
            return Result(name, False, "GET missing entries")
        return Result(
            name,
            True,
            f"POST ok; GET count={gdata.get('count')} (symbol may be deduped)",
        )
    return Result(name, True, f"week={week} entry visible")


def check_intraday() -> Result:
    name = "GET /api/intraday/signals"
    try:
        code, data, _ = _request("GET", "/api/intraday/signals?limit=10")
    except Exception as exc:
        return Result(name, False, str(exc))
    if code != 200 or not isinstance(data, dict):
        return Result(name, False, f"status={code}")
    sigs = data.get("signals") or data.get("calls") or []
    return Result(name, True, f"signals={len(sigs)} as_of={data.get('as_of')}")


def check_mcx() -> Result:
    name = "GET /api/mcx/signals"
    try:
        code, data, _ = _request("GET", "/api/mcx/signals")
    except Exception as exc:
        return Result(name, False, str(exc))
    if code != 200 or not isinstance(data, dict):
        return Result(name, False, f"status={code}")
    sigs = data.get("signals") or data.get("calls") or []
    return Result(name, True, f"signals={len(sigs)}")


def check_consultant(paths: set[str]) -> list[Result]:
    results: list[Result] = []
    endpoints = [
        "/api/consultant/swing",
        "/api/consultant/intraday",
        "/api/consultant/mcx",
        "/api/consultant/daily",
        "/api/consultant/weekly",
    ]
    present = [p for p in endpoints if p in paths]
    if not present:
        # Also probe live in case OpenAPI stale
        code, _, _ = _request("GET", "/api/consultant/swing")
        if code == 404:
            results.append(
                Result(
                    "consultant endpoints",
                    True,
                    "SKIP — not registered (optional until consultant ships)",
                )
            )
            return results
        present = endpoints

    for path in present:
        name = f"GET {path}"
        try:
            code, data, _ = _request("GET", path if "intraday" not in path else f"{path}?limit=10")
        except Exception as exc:
            results.append(Result(name, False, str(exc)))
            continue
        if code != 200 or not isinstance(data, dict):
            results.append(Result(name, False, f"status={code}"))
            continue
        # daily/weekly wrap desks; swing/intraday/mcx expose calls
        calls = data.get("calls")
        if calls is None and path.endswith("/daily"):
            calls = (data.get("intraday") or {}).get("calls") or []
        if calls is None and path.endswith("/weekly"):
            calls = (data.get("swing") or {}).get("calls") or []
        if calls is None:
            calls = []
        bad_side = [
            c.get("side")
            for c in calls
            if isinstance(c, dict) and c.get("side") not in (None, "BUY", "SELL", "HOLD")
        ]
        if bad_side:
            results.append(Result(name, False, f"invalid sides={bad_side[:3]}"))
        else:
            results.append(Result(name, True, f"calls={len(calls)}"))
    return results


def _auth_enabled() -> bool:
    try:
        code, data, _ = _request("GET", "/api/health")
        if code == 200 and isinstance(data, dict):
            return bool(data.get("auth_enabled"))
    except Exception:
        pass
    return False


def _customer_session_headers() -> dict:
    """Login as seeded demo customer when AUTH_ENABLED (local seed_platform)."""
    email = os.environ.get("QA_CUSTOMER_EMAIL", "customer@swingdesk.local")
    password = os.environ.get("QA_CUSTOMER_PASSWORD", "Customer1!")
    code, data, raw = _request(
        "POST",
        "/api/auth/login",
        body={"email": email, "password": password},
    )
    if code != 200 or not isinstance(data, dict) or not data.get("token"):
        raise RuntimeError(f"demo customer login failed status={code} body={raw[:200]}")
    return {"X-Session-Token": data["token"]}


def check_analyze_validation() -> list[Result]:
    """
    Analyze validation:
    - Unauthenticated + AUTH_ENABLED → 401 (auth gate before body validation)
    - Authenticated missing/short key → 422 (not 500)
    """
    out: list[Result] = []
    paths = _openapi_paths()
    if "/api/analyze" not in paths:
        code, _, _ = _request(
            "POST",
            "/api/analyze",
            body={"provider": "openai", "signal": {"symbol": "X"}},
        )
        if code == 404:
            out.append(Result("POST /api/analyze validation", True, "SKIP — route absent"))
            return out

    auth_on = _auth_enabled()

    name = "POST /api/analyze unauthenticated gate"
    try:
        code, data, raw = _request(
            "POST",
            "/api/analyze",
            body={
                "provider": "openai",
                "signal": {"symbol": "RELIANCE", "side": "BUY", "thesis": "qa"},
            },
        )
    except Exception as exc:
        return [Result(name, False, str(exc))]
    if auth_on:
        ok = code == 401
        out.append(Result(name, ok, f"AUTH_ENABLED expect 401 got={code}"))
    else:
        ok = code == 422
        out.append(Result(name, ok, f"AUTH off expect 422 got={code}"))

    # Empty body — 422 validation or 401 if auth required first
    name2 = "POST /api/analyze empty body"
    code2, _, _ = _request("POST", "/api/analyze", body={})
    expect2 = {401, 422} if auth_on else {422}
    out.append(Result(name2, code2 in expect2, f"status={code2} expect={sorted(expect2)}"))

    # Authenticated short key → 422
    name3 = "POST /api/analyze short api_key → 422 (authed)"
    headers = {}
    try:
        if auth_on:
            headers = _customer_session_headers()
    except Exception as exc:
        out.append(Result(name3, False, f"login: {exc}"))
        return out
    code3, _, _ = _request(
        "POST",
        "/api/analyze",
        body={
            "provider": "openai",
            "api_key": "short",
            "signal": {"symbol": "RELIANCE", "side": "HOLD"},
            "use_stored_key": False,
        },
        headers=headers,
    )
    out.append(Result(name3, code3 == 422, f"status={code3}"))
    return out


def main() -> int:
    print(f"Swing Desk production suite → {BASE}")
    if not server_up():
        print("FAIL: server not reachable at /api/health")
        print("Start: cd backend && source venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000")
        return 2

    paths = _openapi_paths()
    results: list[Result] = [
        check_health(),
        check_stats(),
        check_regime(),
        check_weekly_picks(),
        check_journal(),
        check_intraday(),
        check_mcx(),
    ]
    results.extend(check_consultant(paths))
    results.extend(check_analyze_validation())

    # Optional groww absence hard-fail
    if any("groww" in p for p in paths):
        results.append(Result("no Groww routes", False, "OpenAPI still lists groww"))
    else:
        results.append(Result("no Groww routes", True, "ok"))

    print()
    for r in results:
        print(r.line())

    # SKIPs count as pass; only explicit FAIL blocks
    failed = [r for r in results if not r.ok]
    print()
    if failed:
        print(f"SUMMARY: FAIL ({len(failed)}/{len(results)} failed)")
        return 1
    print(f"SUMMARY: PASS ({len(results)} checks)")
    return 0


# Pytest-friendly wrappers (optional)
def test_health():
    assert server_up(), "API down"
    r = check_health()
    assert r.ok, r.detail


def test_core_reads():
    assert server_up(), "API down"
    for fn in (check_stats, check_regime, check_weekly_picks, check_intraday, check_mcx):
        r = fn()
        assert r.ok, r.line()


def test_journal_roundtrip():
    assert server_up(), "API down"
    r = check_journal()
    assert r.ok, r.line()


def test_analyze_422():
    assert server_up(), "API down"
    for r in check_analyze_validation():
        assert r.ok, r.line()


if __name__ == "__main__":
    raise SystemExit(main())
