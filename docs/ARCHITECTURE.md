# Swing Desk — System Architecture

**Product:** Multi-desk research signals terminal (Swing weekly · Intraday daily · MCX/commodities)  
**Stack (current):** FastAPI + SQLite + React CRA  
**API version:** `3.2.0` → target contract `v1` (see [API_CONTRACT.md](./API_CONTRACT.md))  
**Framing:** Consultant-grade BUY / SELL / HOLD *research* calls — not advice, not profit guarantees.

---

## 1. Vision & boundaries

Swing Desk is a **single-operator research company shell**: three desks share one UI shell, one compliance envelope, and one enrichment layer (charts, OI where available, Screener/Yahoo fundamentals). Optional **user-provided LLM API keys** power narrative analysis; keys never become product secrets and are not persisted server-side beyond the request (or short-lived encrypted session if implemented later).

| In scope | Out of scope |
|----------|----------------|
| Signal generation, sizing hints, journal, backtest | Broker order routing / OMS |
| EOD + near-live research feeds | Guaranteed P&L or “tips” |
| BYO LLM narrative on a signal | Hosted LLM billing on our dime |
| Local SQLite research DB | Multi-tenant SaaS auth (phase 2+) |

---

## 2. Logical system diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  React CRA (frontend/src)                                                 │
│  Desks: Swing | Intraday | MCX · Capital · Journal · Browser · Backtest   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ HTTP /api/*
┌───────────────────────────────▼──────────────────────────────────────────┐
│  FastAPI (backend/app)                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │ routers/    │→ │ services/    │→ │ strategy/   │→ │ providers/     │ │
│  │ signals     │  │ compliance   │  │ swing       │  │ kotak_eod      │ │
│  │ analyze     │  │ cache        │  │ intraday    │  │ yahoo_live     │ │
│  │ journal     │  │ signal_store │  │ mcx         │  │ yahoo_eod      │ │
│  │ health      │  │ llm_client   │  │ shared      │  │ screener_fund  │ │
│  └─────────────┘  └──────────────┘  └─────────────┘  └────────────────┘ │
│                           │                                               │
│              ┌────────────▼────────────┐                                  │
│              │ SQLite WAL + JSON cache │                                  │
│              │ eod · indicators · meta │                                  │
│              │ fundamentals_cache.db   │                                  │
│              │ trade_journal.json      │                                  │
│              └─────────────────────────┘                                  │
└──────────────────────────────────────────────────────────────────────────┘
         │ Kotak Neo hist          │ Yahoo 5m chart         │ Screener HTML
         ▼                         ▼                        ▼
   NSE EQ EOD candles        Live bias / MCX proxy     Fundamentals enrich
```

---

## 3. Data planes

Three **independent** data planes. Never mix freshness assumptions across planes in one score without labeling source + age.

### 3.1 EOD plane (Swing desk)

| Concern | Choice |
|---------|--------|
| Primary | **Kotak Neo** historical candles (`KOTAK_CONSUMER_KEY`) |
| Fallback | NSE CM-UDiFF bhavcopy → Yahoo chart EOD |
| Store | SQLite `eod` + `indicators` (WAL) |
| Cadence | Daily ingest; incremental when FRESH/RECENT |
| Cap | `MAX_INGEST_SYMBOLS` (default 500), `INGEST_WORKERS` ≤ 8 |

**Flow:** `POST /api/ingest/latest` → progress bus → NSE gap fill and/or Kotak parallel hist → NIFTY Yahoo series → `recompute_and_store` indicators → `data_source` meta (`nse` / `kotak` / `yahoo` / `mixed` / `demo`).

### 3.2 Live plane (Intraday + MCX)

| Concern | Choice |
|---------|--------|
| Feed | Yahoo Finance chart API, **interval=5m**, range=1d |
| Cache | In-process TTL **~12s** keyed by `symbol|interval|range` |
| Poll hint | API returns `poll_seconds: 15` for UI |
| Equity symbols | Liquid NSE watchlist (`.NS`) |
| MCX | Global futures proxies (`GC=F`, `SI=F`, `CL=F`, …) + `INR=X` context |

Not a broker tape. Outside NSE cash hours, intraday responses are **last-session residue** and must say so.

### 3.3 Fundamentals plane

| Concern | Choice |
|---------|--------|
| Priority | SQLite cache → Screener.in → Yahoo quote → Yahoo quoteSummary → unavailable |
| TTL | **7 days** (`fundamentals_cache.db`) |
| Attach | Optional on swing picks / stock detail; never blocks signal scoring |

---

## 4. Signal lifecycle

```
Universe filter → Feature/score → Side (BUY|SELL|HOLD) → Risk envelope
    → Persist snapshot (optional) → Enrich (fundamentals/charts)
    → Compliance stamp → Serve list / detail → Journal / Analyze (LLM)
```

### 4.1 Side vocabulary (consultant-grade)

Canonical API field: `side` ∈ `BUY` | `SELL` | `HOLD`.

| Desk (today) | Internal bias | Mapped side |
|--------------|---------------|-------------|
| Swing | long candidate / cash | `BUY` / `HOLD` (cash = board-level HOLD) |
| Intraday / MCX | LONG / SHORT / FLAT | `BUY` / `SELL` / `HOLD` |

Legacy aliases `LONG`/`SHORT`/`FLAT` may appear in `tags` or `legacy_side` during migration; clients should prefer `side`.

### 4.2 Per-desk rules (summary)

**Swing (weekly)** — shared by live picks and backtest:

1. Regime gate: NIFTY above SMA20 & SMA50 (else cash / HOLD board)
2. Universe: EQ, price ≥ ₹100, turnover ≥ ₹10 Cr
3. Setup: near HH20, above SMA20/50, RSI 45–75, ROC3 > 0
4. Confirm: volume ≥ 2× vol_ma20 and rising
5. RS vs NIFTY ≥ +3% over 20d
6. Score ≥ 65; top N by capital desk settings
7. Stop / target from ATR & % rules; max hold ~5 sessions

**Intraday** — session bias vs open/prev close, VWAP proxy, short momentum, ORB-lite; hard research disclaimer; suggested risk 0.25–0.5% of capital.

**MCX** — futures tape score → directional bias; user maps to MCX front-month lot/margin; USDINR is context, not a trade signal by default.

### 4.3 Identity & versioning of a signal

Target stable id (detail route):

```
{desk}:{as_of_date_or_iso}:{symbol_or_commodity_id}
```

Examples: `swing:2026-10-24:RELIANCE`, `intraday:2026-10-24T09:45:00Z:TCS`, `mcx:2026-10-24T10:00:00Z:GOLD`.

Each response carries:

- `schema_version` (API JSON schema, e.g. `"1.0"`)
- `strategy_version` (e.g. `"elite_momentum@3.2"`)
- `generated_at` (UTC ISO-8601)
- `disclaimer` (mandatory string; see §7)

---

## 5. Rate limits & caching

| Surface | Limit / TTL | Behavior on pressure |
|---------|-------------|----------------------|
| Kotak hist workers | ≤ 8; pause `INGEST_PAUSE_SEC` (~0.12s) | Cap symbols; retry/backoff; partial universe OK |
| Yahoo live chart | ~12s process cache; UI poll ≥ 15s | Stale cache serve if fetch fails; mark `quote_stale` |
| Yahoo EOD / NIFTY | Burst-sensitive | Prefer Kotak/NSE for equities; Yahoo for index |
| Screener fundamentals | 7d SQLite cache | Return `unavailable` honestly; never invent PE |
| LLM `/api/analyze` | Per-request; client-supplied key | 429/timeout → structured error; no retry storm |
| Ingest concurrency | Single progress lock | Second Force full returns `already_running` |

Caches are **research caches**, not market-data licenses. Provenance fields (`data_source`, `cached`, `feed`) must remain visible in UI chips.

---

## 6. Failure modes

| Failure | Detection | User-visible outcome |
|---------|-----------|----------------------|
| Empty / demo DB | `provenance.data_source == demo` or EMPTY freshness | DEMO badge; message to Refresh / Force full |
| Stale EOD | `max_data_age_days` (default 3) | STALE chip; swing still runs with warning |
| Kotak 429 / auth | ingest progress / feed test | Partial ingest; keep last good EOD |
| NSE bhavcopy down | zero rows from NSE path | Fall through Kotak → Yahoo |
| Yahoo live down | null snapshot | Signal `HOLD`, tag `NO_QUOTE` |
| Fundamentals scrape fail | provider chain exhausts | `fundamentals.status = unavailable` |
| Regime bear / cash | strategy gate | Empty `candidates`, board `HOLD`, radar/message |
| LLM key invalid | provider HTTP 401 | `analyze` 401/502 with safe message; signal unchanged |
| Journal write race | file lock + atomic replace | Last writer wins per week+symbol upsert |
| SQLite lock | WAL + short transactions | Retry once; else 503 on mutating routes |

**Principle:** degrade to **HOLD + honest message**, never fabricate prices or fundamentals.

---

## 7. Disclaimer & compliance layer

Every desk and analyze payload must include a **compliance stamp** (middleware or response assembler):

```json
{
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice. Past patterns and backtests do not guarantee future results. You alone size risk and place orders."
  }
}
```

Rules:

1. UI copy and PDF guides use the same framing (research / education).
2. No endpoint may claim expected return % as a promise; goal planner is **illustrative math** only.
3. Journal is a **personal research log**, not a broker ledger.
4. LLM analysis must restate research-only framing in the model system prompt and in the API response.
5. MCX responses note lot/margin/contract mapping is the user’s responsibility.

---

## 8. Optional LLM analysis

`POST /api/analyze` accepts:

- Signal id or inline signal snapshot
- Optional chart/OI/fundamentals snippets (server may re-fetch from cache)
- **User-provided** `llm_api_key` + `provider` (`openai` | `anthropic` | …)

Server:

1. Never log the raw key
2. Never write the key to SQLite/journal
3. Call provider with a fixed system prompt (research analyst, no guarantees)
4. Return structured narrative: thesis, risks, invalidation, questions — not a new score override unless `mode=critique` is explicitly requested later

If no key: `402`/`400` with “bring your own key” — product stays usable without LLM.

---

## 9. Versioning

| Layer | Scheme | Notes |
|-------|--------|-------|
| App (`FastAPI.version`) | SemVer string e.g. `3.2.0` | Exposed on `/` and `/api/health` |
| API schema | `schema_version` on signal payloads | Breaking JSON → bump major in contract doc |
| Strategy packs | `strategy_version` | Backtest must record the same string |
| DB | Additive SQLite migrations in `store` | No silent column drops |
| Frontend desks | Feature flags via desk tabs | Old `/api/weekly-picks` remains until clients migrate |

**Deprecation:** keep aliases (`/api/weekly-picks`, `/api/intraday/signals`, `/api/mcx/signals`) for one minor train; document redirects in OpenAPI `deprecated: true`.

---

## 10. Target folder layout (do not mass-move yet)

Document-only target. Current files stay put until a dedicated refactor PR.

### 10.1 `backend/app/` (target)

```
backend/app/
├── main.py                 # FastAPI app, CORS, router mounts, version
├── config.py
├── compliance.py           # stamp_disclaimer(), framing constants
├── db/
│   ├── store.py            # SQLite EOD/indicators (from store.py)
│   ├── meta.py
│   └── migrations/         # optional future SQL files
├── providers/
│   ├── kotak_eod.py
│   ├── yahoo_eod.py
│   ├── yahoo_live.py       # from live_quotes.py
│   ├── nse_bhav.py         # from ingest.py NSE pieces
│   └── screener_fundamentals.py
├── services/
│   ├── ingest_pipeline.py  # from pipeline.py
│   ├── progress.py
│   ├── cache.py            # shared TTL helpers
│   ├── journal.py
│   ├── signal_ids.py       # id encode/decode
│   └── llm_analyze.py      # BYO-key client
├── strategy/
│   ├── swing/weekly.py     # from weekly_swing.py
│   ├── intraday/desk.py
│   ├── mcx/desk.py
│   ├── backtest.py
│   └── features.py
├── routers/
│   ├── signals.py          # /api/signals/{desk}, /api/signals/{id}
│   ├── analyze.py          # /api/analyze
│   ├── health.py
│   ├── journal.py
│   ├── ingest.py
│   ├── stocks.py
│   ├── market.py
│   └── backtest.py
└── schemas/                # Pydantic models shared with OpenAPI
    ├── signals.py
    ├── journal.py
    └── analyze.py
```

**Migration rule:** one module per PR; re-export shims from old paths until frontend + scripts updated.

### 10.2 `frontend/src/` (target)

```
frontend/src/
├── index.js
├── App.js                  # shell: desk tabs, chrome, health chips
├── styles/                 # App.css split when needed
├── services/
│   ├── api.js              # axios client
│   └── signalMap.js        # LONG→BUY normalization
├── desks/
│   ├── SwingDesk.js        # extract from App swing board
│   ├── IntradayDesk.js
│   ├── McxDesk.js
│   └── CapitalDesk.js
├── components/             # shared presentational
│   ├── PickCard.js
│   ├── StockModal.js
│   ├── StockBrowser.js
│   ├── WeekJournal.js
│   ├── BacktestSection.js
│   └── ComplianceBanner.js
├── hooks/
│   ├── useDeskPoll.js
│   └── useIngestProgress.js
└── utils/
    └── isoWeek.js
```

---

## 11. Deployment shape (local → production-ready)

**Local (today):** `./start.sh` → uvicorn `:8000` + CRA `:3000` proxy.

**Hardening checklist (not all implemented):**

- Bind CORS to known origins in prod
- Read-only DB backups before Force full
- Structured logging with request id; redact LLM keys
- Health: deep check Kotak configured + latest EOD age + live probe optional
- Rate-limit `/api/analyze` and ingest at reverse proxy
- Explicit `DEMO` vs `LIVE` provenance in every swing response

---

## 12. Related docs

- [API_CONTRACT.md](./API_CONTRACT.md) — REST JSON schemas for signals, analyze, health, journal
- [../README.md](../README.md) — operator quick start & strategy narrative
- [../QUICKSTART.md](../QUICKSTART.md) — short runbook
