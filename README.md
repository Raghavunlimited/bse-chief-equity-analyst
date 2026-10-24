# Swing Desk

Customer-facing research & signals MVP (**v4.0**): auth/RBAC, auditable signals, encrypted LLM vault, demo-labeled market adapter. See [QUICKSTART.md](QUICKSTART.md) and [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md).

NSE weekly swing setups on **liquid NSE cash equities** (not the full BSE/NSE board): momentum breakouts with volume confirmation, relative strength vs NIFTY, and a market-regime gate. When conditions are weak, the desk stays in cash and shows a momentum radar instead.

Default refresh pulls up to **500** NSE EQ names via **concurrent Kotak** workers (`MAX_INGEST_SYMBOLS`, `INGEST_WORKERS=6`). Browse covers ~2,500 listed NSE EQ names; ETFs/illiquids are excluded from the swing scan by design.

## Strategy (shared by live picks and backtest)

1. **Regime** — NIFTY close above SMA20 and SMA50; otherwise no new entries  
2. **Universe** — EQ names, price ≥ ₹100, day turnover ≥ ₹10 Cr  
3. **Setup** — Near 20-day high, above SMA20/50, RSI 45–75, 3-day ROC > 0  
4. **Confirm** — Volume ≥ 2× 20-day average and rising vs prior day  
5. **RS** — Stock 20-day return − NIFTY 20-day ≥ +3%  
6. **Select** — Score ≥ 65; top 2 only  
7. **Risk** — Stop = tighter of 1.2×ATR / 3%; target = higher of 2×ATR / 6%; max hold 5 sessions  

Live screening and backtest call the same `generate_weekly_picks` function.

## Stack

- **Backend:** Python, FastAPI, SQLite (NSE bhavcopy EOD + Yahoo NIFTY series)  
- **Frontend:** React (CRA), Recharts  

## Quick start

```bash
cd bse-chief-equity-analyst
./start.sh
```

- UI: http://localhost:3000  
- API docs: http://localhost:8000/docs  

Manual:

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional
python run_daily_ingest.py
uvicorn app.main:app --reload --port 8000

# Frontend (other terminal)
cd frontend
npm install
npm start
```

## Data

Priority order on **Refresh**:

1. **NSE** CM-UDiFF bhavcopy (when reachable)  
2. **Kotak Neo** (if `KOTAK_CONSUMER_KEY` set — historical needs only the consumer token)  
3. **Yahoo** chart API (works, but rate-limits hard)  

Demo seed is synthetic only — UI shows a **DEMO** badge until live ingest succeeds.

### Kotak Neo setup (primary live EOD)

1. Open **Kotak Neo** app/web → **More** → **Trade API** → Create Application  
2. Copy the consumer token into `backend/.env`:

```bash
KOTAK_CONSUMER_KEY=your_token_here
```

3. Save, click **Test Kotak**, then **Force full**  
4. No TOTP/MPIN needed for historical candles (orders would need them later)

```bash
cd backend && source venv/bin/activate
python run_daily_ingest.py   # live NSE/Yahoo (may rate-limit)
# If live ingest is empty, seed demo history for local UI/backtest:
python seed_demo_data.py
python run_backtest.py
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/ingest/latest` | Fill EOD gap + NIFTY + indicators |
| GET | `/api/weekly-picks` | This week’s setups (or cash) |
| POST | `/api/backtest` | Week-based backtest (costs/gaps) |
| GET | `/api/market-regime` | NIFTY regime |
| GET | `/api/stats` | DB / freshness |
| GET | `/api/stocks` | Browse / search full NSE EQ list |
| GET | `/api/stock/{symbol}` | Detail + Screener financials |
| GET | `/api/chart/{symbol}` | OHLCV |
| GET | `/api/feeds/kotak` | Kotak feed status |

## Risk

This is for research and education, not advice. Markets gap; stops can slip. Size risk per trade (default 2% of capital) and never skip the stop. Past backtest results do not guarantee future returns.
