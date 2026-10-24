# Quick start

## Local (recommended)

```bash
cd bse-chief-equity-analyst
cp backend/.env.example backend/.env   # if needed
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed_platform.py
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend && npm install && npm start
```

Or: `./start.sh` then run `python backend/seed_platform.py` once.

Open http://localhost:3000 and sign in:

| Role | Email | Password |
|------|-------|----------|
| Customer | customer@swingdesk.local | Customer1! |
| Admin | admin@swingdesk.local | AdminDemo1! |

**Personal / real EOD:** set `MAX_INGEST_SYMBOLS=0`, `ALLOW_DEMO_DATA=false`, Kotak key, then **Force full**. Guides: `docs/PERSONAL_USE.md` and `Swing_Desk_Personal_Guide.pdf`. Full EQ list: `backend/nse_eq_symbols.txt` (~2526).

## Docker Compose

```bash
docker compose up --build
```

API :8000 · Web :3000. Seeds demo users/signals on API start.

## Tests

```bash
cd backend && python test_mvp_platform.py
cd frontend && CI=true npm test -- --watchAll=false
```

## Troubleshooting

- **401 on platform routes** — sign in; check `AUTH_ENABLED` and session token.
- **Empty signal ledger** — run `python seed_platform.py`.
- **LLM analyze 422** — configure vault in Settings or pass a one-shot key in the panel.
- **Kotak / live EOD** — optional; set `KOTAK_CONSUMER_KEY`. Demo mode works without it.
- **Fernet errors** — set a stable `SECRET_KEY` (and optional `LLM_FERNET_KEY`) before storing keys; changing the key invalidates vault ciphertext.
