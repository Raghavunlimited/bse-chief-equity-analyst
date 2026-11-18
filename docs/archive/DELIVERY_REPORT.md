# Delivery report — Customer Signals Platform MVP (v4.0.0)

## Repository inspection (pre-implementation)

Existing stack: **FastAPI + React CRA + SQLite**, Kotak EOD, consultant desks (swing/intraday/MCX), BYO LLM analyze, docs under `docs/`. Decision: **extend in place** (not Next.js/Postgres rewrite). See `docs/MVP_ARCHITECTURE.md`.

## Workstreams

| Stream | How delivered |
|--------|----------------|
| Architecture / adapters | Principal-architect agent wrote typed `app/adapters/*` + architecture notes; leads integrated with platform API wrappers |
| Compliance / schema | `docs/SIGNAL_SCHEMA.md`, `docs/DISCLOSURES.md` |
| Implementation | Staff/senior path: `platform_db`, auth/RBAC, vault, admin, FE AuthGate/ledger/admin, Docker, CI |
| QA | `test_mvp_platform.py`, updated analyze validation, FE SettingsDrawer vault tests, `docs/MANUAL_QA_MVP.md` |

Subagents were used for architecture adapters and parallel QA scaffolding; integration and fixes were done in the main delivery pass (adapter signature reconciliation, EmailStr/.local, analyze auth, FE mock).

## Implemented features

- Sign-in / register, session tokens, customer vs admin RBAC
- Append-only signal ledger with revise → new row + prior `revised`
- Demo market-data adapter with prominent DEMO labeling (API + UI banner)
- Methodology `baseline_v1` with explicit `none` when evidence thin
- Encrypted LLM vault (`PUT/GET/DELETE /api/me/llm`) — key never returned
- Analyze requires explicit request; responses marked AI commentary + cited inputs
- Admin: instruments, publish/revise signals, audit log
- Docker Compose, seed script, CI workflow, disclosures & architecture docs

## Commands run (results)

| Command | Result |
|---------|--------|
| `python seed_platform.py` | OK — demo users + signals |
| `python test_mvp_platform.py` | OK — 7 tests |
| `python test_analyze_validation.py` | OK — 9 tests |
| `CI=true npm test -- --watchAll=false` | OK — 8 tests / 3 suites |
| Formatter / dedicated typecheck | Not configured in repo (CRA eslint via tests; no mypy/ruff wired) |
| `npm run build` | Not run in this pass (CI job covers it) |
| `docker compose up --build` | Not run in this pass (files provided) |

## Assumptions

- SQLite + session table is acceptable for single-node MVP
- Consultant legacy routes remain available; platform routes enforce auth when `AUTH_ENABLED=true`
- Demo adapter is default; Kotak remains optional for EOD desks
- No brokerage / order execution

## Known limitations / next steps

1. Wire a contracted live market-data adapter implementing `MarketDataAdapter` (register in `adapters/registry.py`)
2. Move sessions/rate-limits to Redis for multi-instance
3. Optional Postgres migration for `platform_*` tables
4. Jurisdiction-specific legal review before any public offer
5. Gate or separately authenticate remaining mutation routes (ingest) with user roles in addition to `API_KEY`
6. Harden CORS + `SECRET_KEY` / `LLM_FERNET_KEY` for any shared deploy

## Demo access

- Customer: `customer@swingdesk.local` / `Customer1!`
- Admin: `admin@swingdesk.local` / `AdminDemo1!`
