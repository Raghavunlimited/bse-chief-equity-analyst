# MVP Architecture (v4.0)

## Stack decision

The repository already shipped a working **FastAPI + React (CRA) + SQLite** Swing Desk. Per product guidance to *preserve conventions and extend rather than replace*, this MVP **does not** rewrite to Next.js/PostgreSQL.

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | React CRA (TypeScript not required for this extension) | Auth gate, desks, ledger, admin |
| API | FastAPI | Typed Pydantic contracts |
| Persistence | SQLite (same DB file; new platform tables) | Migrations via `CREATE IF NOT EXISTS` on startup |
| Cache/jobs | Not required for MVP | Redis reserved for later ingest workers |
| Market data | Adapter interface + **Demo adapter** | Live Kotak/Yahoo remain optional existing paths |
| Local run | `./start.sh` or Docker Compose | No paid credentials for basic demo |

Postgres is documented as a future swap (`DATABASE_PATH` / connection string); Docker Compose includes a commented Postgres service.

## Boundaries

1. **Frontend** — presentation, session token, never stores LLM keys after vault save.
2. **API** — auth, platform signals, admin, analyze, legacy consultant desks.
3. **Market-data adapters** — `app/adapters/` (`get_quote`, `get_bars`, `get_oi`, `get_financials` + provenance).
4. **Methodology** — `app/signals/methodology.py` (`baseline_v1`) separate from UI/ingest.
5. **LLM** — `llm_analyze.py` + encrypted vault `llm_secrets`; commentary only.
6. **Persistence** — `store.py` (EOD) + `platform_db.py` (users/signals/vault/audit).

## Auth & RBAC

- `AUTH_ENABLED=true` (default): session tokens (`X-Session-Token` / Bearer).
- Roles: `customer`, `admin`. Admin-only `/api/admin/*`.
- Rate limits on login/register/analyze/vault.

## Signals

Append-only `signal_records`. Revise marks prior `revised` and inserts a new row with `supersedes_id`. Directions: `buy` | `sell` | `none`.

## Provenance

Every platform market payload and signal carries `data_mode`: `live` | `delayed` | `stale` | `demo`. Demo is the default adapter.

## Known production gaps

- SQLite single-node; multi-instance needs Postgres + shared session store.
- In-memory rate limiter is per-process.
- Consultant desks remain largely ungated for backward compatibility; platform routes require auth.
- No brokerage / order routing (by design).
- Jurisdiction compliance is configurable text, not certified.
- Live market-data adapter beyond Kotak EOD / Yahoo 5m still needs a contracted provider.
