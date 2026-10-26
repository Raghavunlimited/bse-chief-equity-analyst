# Swing Desk — Personal use guide (v5.12 strategy evaluation)

This is the guide to use **now**. Demo/mock adapters are **forbidden**. Auth is off by default — the UI boots straight into the personal desk on **loopback only** (`127.0.0.1`). Do not expose the API to a public network without auth. Ops/backup: [`OPS.md`](OPS.md).

## What is real vs what is not

| Piece | Real? | Notes |
|-------|--------|--------|
| Stock prices on Swing / stock page | **EOD close** (`price_kind=eod_close`, state `EOD`) | Kotak settlement — never labeled as LTP |
| Intraday / Index LTP | **LiveQuote** | **Kotak WS** (`native_batch` / apifeed HS) → `LIVE` when connected+subscribed. **Yahoo 5m** → `FALLBACK` only if `ALLOW_YAHOO_LTP_FALLBACK=true` (default). Never labeled broker live. Age >`LIVE_QUOTE_STALE_SEC` → `STALE` + halt. Start WS: `POST /api/kotak/session/login` (TOTP). Status: `GET /api/kotak/feed/status` |
| 5m history / expectancy | **SQLite `bars_5m`** | Completed IST-session 5m bars only (deduped). Intraday/Index STRONG gates use the **same** 5m strategy cores as the desk — **no daily proxy**. Insufficient history → gate fails with explicit reason; never “proven” from a backtest alone |
| Kotak protocol note | HS/apifeed | Matches Kotak Market Data WebSocket guide (`native_batch`). Kotak announced **SFeed migration by 15 Sep 2026** — this desk has **not** migrated yet |
| Process health vs data ready | Separate | `/api/health` = process up; `/api/health/ready` = EOD FRESH for Swing (not LTP) |
| Session clock | Trading days IST 09:15–15:30 | Weekends = `WEEKEND`. Holidays from configurable `nse_holidays.json` (+ `NSE_EXTRA_HOLIDAYS`) — **operator-maintained snapshot, not live NSE sync** |
| Swing EOD ingest | Manual + scheduled | Refresh / Force full still work. Scheduler default **18:45 IST** on trading days after settle (**18:30**). Idempotent via ingest journal. Status: `GET /api/ingest/status` |
| Browse / search all NSE EQ names | **Yes** | Full scrip master (~2500 EQ cash) |
| Swing / Intraday / Index calls | **Rule-based on typed feeds** | Research screens — not broker tips |
| Commodities (MCX tab) | **Yahoo global futures proxy** | USD continuous (GC=F etc.) + USDINR — **not** MCX INR contracts/lots. Confidence capped; no expectancy STRONG gate |
| Charts (stock modal) | **Yahoo / Kotak EOD OHLCV** | Intervals 1m–1D; IST labels; source + freshness badges; null bars skipped (not filled). EMA matches desk `index_core.ema`; chart RSI is Wilder (desk uses simple RSI). Last price = bar close unless Kotak `/live` quote |
| Option PCR / chain / walls / OI viz | **Optional** | Kotak login + Activate only. Idle = **unavailable** (not zero PCR/OI). Call/put OI chart via `/oi-viz`. IV is model-derived; ΔOI is session baseline. OI/PCR are **not** trade signals. Not CI e2e-verified |
| L2 market depth | **Not chart-verified** | Subscribe path exists; empty/missing books labeled unavailable — not shown as thin liquidity |
| Trade journal / capital | **User-entered** | `/api/ledger` — open/closed trades, partial exits, fees, deposits/withdrawals, audit corrections. Not broker fills. Unrealized only when a quote is available (separately labeled). Week Journal remains a lighter research log |
| Risk position size | **Research calc** | `/api/position-sizing/calculate` — fixed-fractional size from capital, risk %, entry/stop, costs, verified lot/multiplier. Missing/stale/unverified inputs → unavailable (no fabricated size). Not an order; does not place trades. MCX proxy lots unavailable |
| Market events | **Identifiable sources only** | `/api/market-events` — NSE holiday snapshot + operator `market_events.json` + optional Kotak F&O expiries when cached. Source, time+TZ, last update, feed status per event. Stale/unavailable feeds labeled. No invented dates/forecasts/outcomes/impact; no commercial calendar scrape/license claimed |
| Strategy evaluation | **Research evidence** | `/api/strategy-evaluation` — walk-forward / OOS for audit-confirmed rules (swing EOD, intraday/index 5m when history exists). Costs, sample-size gates, regimes, drawdown, baselines, bias checklist. Never crowns a “best” or proven strategy. Options put/call withheld without explicit testable rules; OI/PCR not a directional signal |
| Demo seeds / demo adapter | **Removed** | `seed_demo_data` refuses; `/api/platform/demo/signals` → 410 |
| Optional LLM notes | Your key + model | Commentary only |

There is **no brokerage / order execution**. Calls are research screens, not guaranteed profits.

## One-time setup

```bash
cd bse-chief-equity-analyst
# backend/.env — see .env.example:
#   KOTAK_CONSUMER_KEY=<Neo Trade API consumer key>
#   SECRET_KEY=<unique, not the example default>
#   MAX_INGEST_SYMBOLS=0
#   AUTH_ENABLED=false
#   BIND_HOST=127.0.0.1
#   ALLOW_PUBLIC_BIND=false
#   MARKET_DATA_ADAPTER=live
#   LIVE_QUOTE_STALE_SEC=5
#   ALLOW_YAHOO_LTP_FALLBACK=true
#   BARS_5M_RETENTION_DAYS=45
#   EOD_INGEST_SCHEDULE_ENABLED=true
#   INGEST_WORKERS=6
# Optional LIVE: POST /api/kotak/session/login with TOTP
# Backup: ./scripts/backup_sqlite.sh

./start.sh
# or: uvicorn on 127.0.0.1:8000 + HOST=127.0.0.1 npm start
```

- UI: http://127.0.0.1:3000  
- API: http://127.0.0.1:8000 (`/docs` when enabled)  
- Health posture: `GET /api/health` → `security.production_ready_claim` is always **false** for this personal build

## Desks (use these)

1. **Swing** — Weekly NSE momentum. BEAR / NIFTY below SMA50 → **cash by design**. Radar = watchlist, not a forced buy.
2. **Intraday** — NSE cash bias from Kotak WS LTP when connected, else Yahoo 5m **FALLBACK** (explicit). Session-aware; size ~0.25–0.5% risk.
3. **Index** — **Nifty + BankNifty** multi-timeframe bias (`index_mtf_vwap_v1`): daily SMA regime + 5m EMA9/21 + VWAP + RSI + BN vs Nifty spread. Map to F&O yourself. PCR / walls appear only when Kotak option chain is activated.
4. **Commodities (MCX tab)** — Yahoo **global futures proxy** (usually USD) + USDINR. Not exchange-listed MCX INR contracts; related MCX names are unvalidated hints. No lot sizing / expectancy STRONG gate.
5. Open any symbol → **pro chart** (candles/line, volume, SMA20/50, 1M–1Y) + Screener financials.
6. **Force full** when you want all NSE EQ EOD refreshed (hours). **Refresh** for incremental.

## How to read today’s tape

- Swing `as_of` = last Kotak EOD date (often prior session). Live broker LTP can differ intraday.
- Index / Intraday refresh while the NSE session is open (~09:15–15:30 IST).
- Cash weeks are intentional: do **not** force radar names just because they bounce.

## Personal checklist

- [ ] Kotak key in `.env`, unique `SECRET_KEY`, `BIND_HOST=127.0.0.1`, `MAX_INGEST_SYMBOLS=0`
- [ ] Force full at least once for your universe
- [ ] Periodic DB backup: `./scripts/backup_sqlite.sh`
- [ ] Use **Index** tab for Nifty / BankNifty bias before F&O
- [ ] Log ideas in Week Journal — desk does not place orders
- [ ] Treat LLM output as notes, never as an authoritative signal
- [ ] Do not publish ports / `0.0.0.0` with auth off
