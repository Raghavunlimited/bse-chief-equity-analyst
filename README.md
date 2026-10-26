# Swing Desk

Personal **research-only** multi-desk (Swing · Intraday · Index · Commodities proxy) for NSE cash / index work. Live Kotak EOD + optional Kotak WebSocket LTP; Yahoo as explicit research fallback. **No order execution.**

Canonical guide: [`docs/PERSONAL_USE.md`](docs/PERSONAL_USE.md) · Ops / backup: [`docs/OPS.md`](docs/OPS.md) · Upgrade tracker: [`DESK_UPGRADE_TRACKER.md`](DESK_UPGRADE_TRACKER.md)

This build targets a **single-operator local machine** (`AUTH_ENABLED=false`, loopback bind). It is **not** claimed production-ready for public or multi-user hosting.

## Quick start

```bash
cd bse-chief-equity-analyst
cp backend/.env.example backend/.env   # set KOTAK_CONSUMER_KEY + unique SECRET_KEY
./start.sh
```

- UI: http://127.0.0.1:3000  
- API: http://127.0.0.1:8000 (`/docs` when `ENABLE_API_DOCS=true`)  

`./start.sh` binds **127.0.0.1** by default. Do not publish an unauthenticated desk to a network.

Manual backend:

```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Data (honest)

| Desk | Source |
|------|--------|
| Swing | Kotak EOD (SQLite) — `price_kind=eod_close` |
| Intraday / Index LTP | Kotak WS when live, else Yahoo 5m **FALLBACK** |
| Commodities tab | Yahoo global futures **proxy** (not MCX INR lots) |
| Option PCR / walls | Optional — Kotak login + activate only |

Demo / synthetic adapters and `seed_demo_data.py` / `seed_platform.py` are **refused**.

### Kotak Neo

1. Neo → Trade API → consumer token → `KOTAK_CONSUMER_KEY` in `backend/.env`  
2. Force full for EOD universe  
3. Optional LIVE: `POST /api/kotak/session/login` with TOTP  

## Strategy (Swing)

Shared `generate_weekly_picks` for live picks and classic backtest: NIFTY regime gate, liquid EQ universe, breakout/pullback + volume/RS/score, ATR stops. Intraday/Index STRONG gates use walk-forward expectancy on persisted 5m bars when history allows.

## Ops

- Health: `GET /api/health` (liveness + security posture + schema)  
- Ready: `GET /api/health/ready` (EOD FRESH — not “production ready”)  
- Backup: `./scripts/backup_sqlite.sh`  

## Risk

Research and education only — not investment advice. Markets gap; stops can slip. Past expectancy / backtest results do not guarantee future returns.
