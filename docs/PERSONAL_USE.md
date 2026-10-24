# Swing Desk — Personal use guide (real data)

This guide is for **your own** research desk. No sales pitch. No demo mode required.

## What is real vs what is not

| Piece | Real? | Notes |
|-------|--------|--------|
| Stock prices on Swing desk / stock page | **Yes — Kotak EOD** | Previous session OHLC (e.g. KPIGREEN close ₹287.30 on 2026-10-23) |
| Browse / search all NSE EQ names | **Yes** | Full scrip master (~2500 EQ cash). ETFs/bonds filtered out |
| EOD candles after Force full | **Yes — Kotak** | Size controlled by `MAX_INGEST_SYMBOLS` (0 = all) |
| Swing / Intraday / MCX consultant calls | **Real rules on real data** | Not broker tips. BEAR = intentional cash |
| Platform “Signal ledger” DEMO rows | Sample seed | Ignore for trading; or don’t run `seed_platform.py` |
| Optional LLM notes | Your key + model | Commentary only |

There is **no brokerage / order execution**. Calls are research screens, not guaranteed profits.

## One-time setup

```bash
cd bse-chief-equity-analyst
cp backend/.env.example backend/.env   # if needed
# Edit backend/.env:
#   KOTAK_CONSUMER_KEY=<your Neo Trade API consumer key>
#   MAX_INGEST_SYMBOLS=0          # ALL NSE EQ
#   ALLOW_DEMO_DATA=false
#   AUTH_ENABLED=false            # personal single-user (optional)
#   INGEST_WORKERS=6              # max 8

cd backend && source venv/bin/activate   # or .venv
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Other terminal:

```bash
cd frontend && npm start
```

Or: `./start.sh`

UI: http://localhost:3000  
API: http://localhost:8000/docs  

Kotak key: Neo app → More → Trade API → Create Application → paste consumer token into `.env`.

## Pull **all** NSE EQ EOD (not just 500)

Default is now **`MAX_INGEST_SYMBOLS=0`** (unlimited = full EQ cash list).

1. Confirm listed size: open `/api/stats` → `coverage.listed_eq_approx` (~2500).
2. In the UI click **Force full** (or POST `/api/ingest/latest?force=true`).
3. Watch progress: `/api/ingest/progress`.

**Expect hours** for ~2500 names (Kotak rate limits). If you get 429s, lower `INGEST_WORKERS` to 3–4 or raise `INGEST_PAUSE_SEC` slightly.

List symbols to a file anytime:

```bash
cd backend && source venv/bin/activate
python -c "from app.universe_nse import all_eq_symbols; open('nse_eq_symbols.txt','w').write('\n'.join(all_eq_symbols())); print(len(all_eq_symbols()))"
```

## How to use the desks

1. **Swing** — Weekly NSE momentum. If regime is BEAR, desk stays **cash** (by design). Use Week Planner + journal. Radar = watchlist, not a forced buy.
2. **Intraday** — Near-live bias board (Yahoo 5m where available). Smaller size; session-aware.
3. **MCX** — Commodity directional tape (map to front-month MCX yourself).
4. Open any symbol → chart + Screener financials (cached).
5. **Settings** — optional LLM key (server vault when auth on; personal AUTH off still works for desks).
6. **Refresh data** — incremental; **Force full** — full universe refresh.

## Why a live site might show ₹288.90 while the app shows ₹287.30

App stock card = **previous session official close** (Kotak EOD). Brokers often show **last traded price**. On weekends the app correctly stays on Friday’s close.

## Personal checklist

- [ ] Kotak key in `.env`
- [ ] `ALLOW_DEMO_DATA=false`
- [ ] `MAX_INGEST_SYMBOLS=0`
- [ ] Force full completed at least once
- [ ] `/api/health` shows kotak configured; stock page shows latest EOD date
- [ ] Ignore DEMO signal-ledger rows if present

## Honest limits

- Full board ingest ≠ every name will pass the weekly screen (liquidity / score filters still apply).
- Cash weeks in BEAR are normal, not a broken app.
- Past backtests do not guarantee future results.
