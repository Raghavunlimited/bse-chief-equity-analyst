#!/usr/bin/env python3
"""
World-class acceptance tests for Swing Desk.

Prefers a live API at http://localhost:8000. If the server is down,
falls back to import-level checks against the FastAPI app (same assertions
where possible). Groww presence always FAILs — never skipped.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

BASE = "http://localhost:8000"
GROWW_PATH = "/api/feeds/groww"
TIMEOUT = 60


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail

    def line(self) -> str:
        tag = "PASS" if self.ok else "FAIL"
        extra = f" — {self.detail}" if self.detail else ""
        return f"[{tag}] {self.name}{extra}"


def _http_json(method: str, path: str) -> tuple[int, Any]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body) if body else None


def api_up() -> bool:
    try:
        code, _ = _http_json("GET", "/api/health")
        return code == 200
    except Exception:
        return False


def _collect_route_paths_from_app(app) -> set[str]:
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    # Also surface OpenAPI paths if schema builds cleanly
    try:
        for p in (app.openapi() or {}).get("paths", {}):
            paths.add(p)
    except Exception:
        pass
    return paths


def _import_app():
    """Load FastAPI app for offline / route inspection."""
    from pathlib import Path

    backend = Path(__file__).resolve().parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.main import app

    return app


def _prefer_venv_python() -> None:
    """Re-exec under backend/venv if system python lacks FastAPI."""
    if "fastapi" in sys.modules:
        return
    try:
        import fastapi  # noqa: F401

        return
    except ImportError:
        pass
    from pathlib import Path

    venv_py = Path(__file__).resolve().parent / "venv" / "bin" / "python"
    if venv_py.is_file() and Path(sys.executable).resolve() != venv_py.resolve():
        import os

        os.execv(str(venv_py), [str(venv_py), *sys.argv])


def _paths_contain_groww(paths: set[str]) -> list[str]:
    hits = {
        p
        for p in paths
        if GROWW_PATH in p or "/feeds/groww" in p
    }
    return sorted(hits)


def check_no_groww_routes(*, live: bool) -> CheckResult:
    name = "1. No /api/feeds/groww (OpenAPI + app routes)"
    paths: set[str] = set()
    notes: list[str] = []

    if live:
        try:
            code, spec = _http_json("GET", "/openapi.json")
            if code != 200 or not isinstance(spec, dict):
                return CheckResult(name, False, f"openapi.json HTTP {code}")
            paths |= set(spec.get("paths", {}))
            notes.append(f"openapi={len(spec.get('paths', {}))}")
        except Exception as e:
            return CheckResult(name, False, f"openapi fetch: {e}")

    # Import-level route inspection (required when API is down; best-effort when live)
    import_err: str | None = None
    try:
        app = _import_app()
        paths |= _collect_route_paths_from_app(app)
        notes.append("import=app.main")
    except Exception as e:
        import_err = str(e)

    try:
        import app.routes as routes_mod  # type: ignore

        for attr in dir(routes_mod):
            obj = getattr(routes_mod, attr, None)
            rpath = getattr(obj, "path", None)
            if isinstance(rpath, str):
                paths.add(rpath)
        notes.append("import=app.routes")
    except ModuleNotFoundError:
        pass  # project uses app.routers — OK
    except Exception as e:
        if not live:
            return CheckResult(name, False, f"import app.routes: {e}")

    if not paths:
        detail = import_err or "no routes discovered"
        return CheckResult(name, False, detail)

    groww_hits = _paths_contain_groww(paths)
    if groww_hits:
        return CheckResult(
            name,
            False,
            f"Groww feed still registered: {groww_hits}",
        )

    detail = f"checked {len(paths)} paths; kotak-only feeds OK ({', '.join(notes)})"
    if import_err and live:
        detail += f"; import skipped ({import_err})"
    return CheckResult(name, True, detail)

def check_health(*, live: bool) -> CheckResult:
    name = "2. GET /api/health has kotak, no groww"
    try:
        if live:
            code, data = _http_json("GET", "/api/health")
            if code != 200:
                return CheckResult(name, False, f"HTTP {code}")
        else:
            app = _import_app()
            # Call the endpoint function directly
            from app.main import health

            data = health()
    except Exception as e:
        return CheckResult(name, False, str(e))

    feeds = (data or {}).get("feeds") or {}
    if "kotak" not in feeds:
        return CheckResult(name, False, f"missing feeds.kotak; keys={list(feeds)}")
    if "groww" in feeds:
        return CheckResult(
            name,
            False,
            "FAIL: feeds.groww still present in /api/health — Groww must be removed",
        )
    return CheckResult(name, True, f"feeds={list(feeds.keys())}")


def check_stocks_total(*, live: bool) -> CheckResult:
    name = "3. GET /api/stocks total ≈ 2000+"
    try:
        if live:
            code, data = _http_json("GET", "/api/stocks?page=1&page_size=1")
            if code != 200:
                return CheckResult(name, False, f"HTTP {code}")
        else:
            from app.routers.stocks import list_stocks

            data = list_stocks(page=1, page_size=1)
    except Exception as e:
        return CheckResult(name, False, str(e))

    total = (data or {}).get("total")
    if total is None:
        return CheckResult(name, False, f"no total field; keys={list((data or {}).keys())}")
    if int(total) < 2000:
        return CheckResult(name, False, f"total={total} (expected ≥ 2000)")
    return CheckResult(name, True, f"total={total}")


def check_reliance_fundamentals(*, live: bool) -> CheckResult:
    name = "4. GET /api/stock/RELIANCE fundamentals"
    try:
        if live:
            code, data = _http_json("GET", "/api/stock/RELIANCE")
            if code != 200:
                return CheckResult(name, False, f"HTTP {code}")
        else:
            from app.routers.stocks import stock_detail

            data = stock_detail("RELIANCE")
    except Exception as e:
        return CheckResult(name, False, str(e))

    fund = (data or {}).get("fundamentals") or {}
    available = fund.get("available")
    message = fund.get("message")
    if available is True:
        return CheckResult(name, True, f"available=True source={fund.get('source')}")
    if message and isinstance(message, str) and message.strip():
        return CheckResult(
            name,
            True,
            f"graceful message (available={available}): {message[:80]}",
        )
    return CheckResult(
        name,
        False,
        f"expected available=True or graceful message; got {fund!r}",
    )


def check_weekly_picks(*, live: bool) -> CheckResult:
    name = "5. GET /api/weekly-picks status + radar"
    try:
        if live:
            code, data = _http_json("GET", "/api/weekly-picks?fundamentals=false")
            if code != 200:
                return CheckResult(name, False, f"HTTP {code}")
        else:
            from app.routers.picks import weekly_picks

            data = weekly_picks(as_of=None, fundamentals=False)
    except Exception as e:
        return CheckResult(name, False, str(e))

    if "status" not in (data or {}):
        return CheckResult(name, False, f"missing status; keys={list((data or {}).keys())}")
    radar = (data or {}).get("radar")
    if not isinstance(radar, list):
        return CheckResult(name, False, f"radar must be a list; got {type(radar).__name__}")
    return CheckResult(
        name,
        True,
        f"status={data.get('status')} radar_len={len(radar)}",
    )


def check_stats(*, live: bool) -> CheckResult:
    name = "6. GET /api/stats symbol_count + coverage.listed_eq_approx"
    try:
        if live:
            code, data = _http_json("GET", "/api/stats")
            if code != 200:
                return CheckResult(name, False, f"HTTP {code}")
        else:
            from app.routers.ingest import stats

            data = stats()
    except Exception as e:
        return CheckResult(name, False, str(e))

    if "symbol_count" not in (data or {}):
        return CheckResult(name, False, f"missing symbol_count; keys={list((data or {}).keys())}")
    coverage = (data or {}).get("coverage") or {}
    if "listed_eq_approx" not in coverage:
        return CheckResult(
            name,
            False,
            f"missing coverage.listed_eq_approx; coverage={coverage!r}",
        )
    return CheckResult(
        name,
        True,
        f"symbol_count={data.get('symbol_count')} listed_eq_approx={coverage.get('listed_eq_approx')}",
    )


def run_all() -> int:
    live = api_up()
    mode = "LIVE localhost:8000" if live else "IMPORT-LEVEL (API down)"
    print(f"Swing Desk world-class QA — mode: {mode}\n")

    checks: list[Callable[..., CheckResult]] = [
        check_no_groww_routes,
        check_health,
        check_stocks_total,
        check_reliance_fundamentals,
        check_weekly_picks,
        check_stats,
    ]

    results = [fn(live=live) for fn in checks]
    for r in results:
        print(r.line())

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    print(f"\nSummary: {passed}/{len(results)} passed, {failed} failed")
    if failed:
        groww_fails = [
            r
            for r in results
            if not r.ok
            and (
                "Groww feed still registered" in r.detail
                or "feeds.groww still present" in r.detail
            )
        ]
        if groww_fails:
            print(
                "GROWW STILL PRESENT — treat as hard FAIL (do not ignore / skip)."
            )
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    _prefer_venv_python()
    raise SystemExit(run_all())
