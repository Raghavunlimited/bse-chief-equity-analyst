# Quick start

## Local (recommended)

```bash
cd bse-chief-equity-analyst
cp backend/.env.example backend/.env
# Set KOTAK_CONSUMER_KEY=… and a unique SECRET_KEY=
# Leave API_KEY empty for personal UI; AUTH_ENABLED=false; BIND_HOST=127.0.0.1
./start.sh
```

Or manually:

```bash
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# BIND_HOST defaults to 127.0.0.1 — do not use 0.0.0.0 with AUTH off
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm install && HOST=127.0.0.1 DANGEROUSLY_DISABLE_HOST_CHECK=true BROWSER=none npm start
```

Open http://127.0.0.1:3000 — **personal desk, AUTH off, loopback only**.

**Required `.env`:** `MARKET_DATA_ADAPTER=live`, `AUTH_ENABLED=false`, `LIVE_QUOTE_STALE_SEC=5`, `KOTAK_CONSUMER_KEY=…` (for Kotak EOD/LIVE), `MAX_INGEST_SYMBOLS=0`, `BIND_HOST=127.0.0.1`. Demo adapter / `seed_demo_data` / `seed_platform` are **forbidden**. Force full for EOD.

Beginner guide: [`docs/PERSONAL_USE.md`](docs/PERSONAL_USE.md) · Ops/backup: [`docs/OPS.md`](docs/OPS.md)

## Docker Compose

```bash
docker compose up --build
```

API http://127.0.0.1:8000 · Web http://127.0.0.1:3000 (ports bound to loopback). Requires `KOTAK_CONSUMER_KEY` in the environment for live EOD. No demo seed.

## Tests (CI-equivalent)

```bash
cd backend
export AUTH_ENABLED=false SECRET_KEY='ci-test-secret-key-32chars-min!!' MARKET_DATA_ADAPTER=live
export EOD_INGEST_SCHEDULE_ENABLED=false
python -c "from app.signals.methodology import score_evidence; assert score_evidence({})['direction']=='none'"
python test_methodology.py
python test_phase1_market.py test_phase2_kotak_feed.py test_phase2_provider.py
python test_phase3_bars.py test_phase3_option_chain.py
python test_phase4_eod.py test_phase4_chart.py
python test_phase5_mcx.py test_phase5_expectancy.py
python test_phase6_chart.py test_phase7_ops.py
python test_options_oi.py test_trade_ledger.py test_position_sizing.py
python test_market_events.py test_strategy_evaluation.py
python test_signal_availability.py test_kotak_adapter_contract.py
python test_crypto_adapters.py test_mvp_platform.py test_analyze_validation.py
cd ../frontend && CI=true npm test -- --watchAll=false && npm run build
```

## Troubleshooting

- **API refuses boot on 0.0.0.0** — expected with `AUTH_ENABLED=false`. Use `BIND_HOST=127.0.0.1`.
- **Empty EOD / not ready** — set Kotak key and Force full. Demo seed is refused.
- **Empty Signal ledger** — normal. Ledger is optional published notes, not an auto-feed of desk cards. Use desk boards; optionally **Publish notes** with data_mode live/delayed/eod (demo rows stay hidden).
- **Only HOLD / “no qualifying signal” on Swing** — often cash/BEAR regime (e.g. Nifty below SMA50). Strategy working, not a crash.
- **Intraday/Index “data blocked”** — after-hours freeze or missing/FALLBACK quotes. Yahoo is never labeled broker LIVE.
- **LLM explain 422** — configure vault in Settings or pass a one-shot key in the panel. LLM explains only; it does not create or change signals.
- **Holiday calendar STALE** — operator snapshot; verify NSE circular before updating `nse_holidays.json` / `as_of`.
- **Walk-forward 401 when API_KEY set** — send `X-API-Key`, or leave `API_KEY` empty for personal loopback UI.
- **Fernet errors** — set a stable unique `SECRET_KEY` before storing LLM keys.
- **Backup** — `./scripts/backup_sqlite.sh`
