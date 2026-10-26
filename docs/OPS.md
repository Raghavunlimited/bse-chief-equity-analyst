# Swing Desk — Operations (Phase 7)

Personal / local research desk. **Not** a multi-tenant production SaaS claim.

## Deployment model

| Setting | Personal default | Meaning |
|---------|------------------|---------|
| `AUTH_ENABLED` | `false` | Single operator on this machine |
| `BIND_HOST` | `127.0.0.1` | Loopback only via `./start.sh` |
| `ALLOW_PUBLIC_BIND` | `false` | Boot **refuses** `0.0.0.0` + auth off unless set true |
| `CORS_ORIGINS` | empty → localhost list | No default `*` |
| `ENABLE_API_DOCS` | `true` | Fine on loopback; set `false` if you ever expose the API |
| `MARKET_DATA_ADAPTER` | `live` | Demo/mock hard-rejected |

Health: `GET /api/health` includes `security` posture (`production_ready_claim: false`) and SQLite schema check. Ready: `GET /api/health/ready` is **EOD freshness only** (not LTP, not “prod ready”).

## Secrets

- Keep secrets in `backend/.env` (gitignored). Never commit keys.
- Rotate `SECRET_KEY` if it was ever shared; changing it invalidates session/Fernet vault material.
- API errors / feed status go through `sanitize_error_text` (redacts token/mpin/secret/api_key/consumer_key patterns).
- Optional `API_KEY` (header `X-API-Key`) when **non-empty** gates:
  - prefixes: `/api/ingest`, `/api/backtest`, `/api/ledger`, `/api/feeds/kotak/test`, `/api/kotak/session/login`
  - `POST /api/journal`
  - **expensive strategy eval:** `POST /api/strategy-evaluation/evaluate` and `GET /api/strategy-evaluation?run_harness=true`
  - **Not gated:** `GET …/meta`, `…/audit`, `GET …?run_harness=false`; `POST /api/analyze` (vault/BYOK); position-sizing calculate
- **Local-dev implication:** leave `API_KEY` empty on loopback so the Strategy Evaluation “Run walk-forward” button works (CRA does not attach `X-API-Key`). When you set `API_KEY` for a hardened local/network bind, call evaluate with curl/`X-API-Key` or expect 401 from the UI button. Do **not** enable `AUTH_ENABLED` solely for this route — optional key gate is the least-disruptive posture.

## SQLite backup & recovery

Database: `backend/data/swing_trader.db` (path override: `DATABASE_PATH`).

```bash
# Backup (prefer while API is idle; online .backup used when sqlite3 CLI exists)
./scripts/backup_sqlite.sh
# or: BACKUP_DIR=/path/to/backups ./scripts/backup_sqlite.sh /path/to/swing_trader.db
```

Restore:

1. Stop API / `start.sh`.
2. `cp backend/data/backups/swing_trader_YYYYMMDD….db backend/data/swing_trader.db`
3. If you copied WAL/SHM companions during a cold `cp`, restore those too; after sqlite3 `.backup` a single file is enough.
4. Start API; confirm `GET /api/health` → `schema.ok` and `/api/health/ready`.

There is **no** Alembic. Tables are created with `CREATE IF NOT EXISTS` on startup / first use. `schema` on `/api/health` lists required vs present tables.

## CI

GitHub Actions runs methodology + `test_phase1`…`test_phase7` + crypto/mvp/analyze, then frontend test + build. Do not skip failing phase tests.

## Intentional limitations

- Process-local Kotak feed hub / quote cache (no multi-instance sticky feed).
- In-process EOD scheduler (dies with the API process).
- Holiday file `backend/app/data/nse_holidays.json`: the desk operator updates it from the NSE cash-market holiday circular on nseindia.com. There is no live download. Current committed `as_of` is **2026-01-15** with `stale_after_days: 120`. An old `as_of` marks that holiday source **STALE — not a current calendar** on purpose. Leave `as_of` and the holiday dates unchanged until you have checked the circular yourself; the UI must never present a stale feed as current.
- L2 depth / option chain / Kotak WS e2e **not** claimed verified in CI.
- MCX tab = Yahoo global futures proxy, not INR MCX lots.
- No order execution.

## Docker

`docker compose` publishes **127.0.0.1:8000** and **127.0.0.1:3000**. Container sets `ALLOW_PUBLIC_BIND=true` for internal `0.0.0.0` listen only. Do not remap ports to all interfaces without auth.
