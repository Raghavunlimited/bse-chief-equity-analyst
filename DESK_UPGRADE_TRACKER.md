# Desk Upgrade Tracker

**Repository:** `bse-chief-equity-analyst`  
**App version string (code):** `5.12.4-api-key-evaluate` (`backend/app/main.py`)  
**Git HEAD:** `86fd559` on `main` (clean vs `origin/main` except audit doc edits this pass)  
**Audit date:** 2026-10-26  
**Current upgrade phase:** **FINAL AUDIT (post-remediation) COMPLETE** — see `FINAL_REVERSE_ENGINEERING_AUDIT.md`; **STOP — no further fixes this pass**  
**Release readiness claim:** **Not production-ready for public/multi-user hosting** — personal/local research desk only (`security.production_ready_claim: false`)  

---

## Phase status board

| Phase | Name | Status |
|-------|------|--------|
| 0 | Reverse-engineering audit and baseline | **COMPLETE** |
| 1 | Truthful market-data contracts and stale-data safety | **COMPLETE** |
| 2 | Broker live-feed path and explicit fallback | **COMPLETE** |
| 3 | Persistent 5m history and strategy-valid expectancy | **COMPLETE** |
| 4 | Scheduled, holiday-aware EOD ingestion | **COMPLETE** |
| 5 | MCX correctness and desk-specific validation | **COMPLETE** |
| 6 | Charts, optional depth/options, polish | **COMPLETE** |
| 7 | Ops, security, CI, release readiness | **COMPLETE** |

---

## Phase 0 — Audit findings and evidence

### 0.1 Product thesis (verified)

Personal, research-only multi-desk NSE/MCX analysis UI + FastAPI backend. **No order execution** in routers or adapters. Disclaimers present in signal models and desk modules. Not an OMS.

### 0.2 Architecture map

```
Providers
  Kotak Neo historical (consumer key) ──► kotak_eod / ingest ──► SQLite eod+indicators
  NSE bhavcopy (when reachable)       ──► ingest pipeline
  Yahoo chart API                     ──► live_quotes (5m) / yahoo_eod / chart_data / MCX futures
  Kotak Neo WS (TOTP session)         ──► kotak.feed_hub ──► live_quotes prefer-path
  Screener.in                         ──► fundamentals cache DB

Strategy
  weekly_swing.generate_weekly_picks ──► swing_calls ──► expectancy.gate
  strategy.intraday                  ──► intraday_calls ──► expectancy.gate
  strategy.index_desk (index_mtf_vwap_v1) ──► index_calls ──► expectancy.gate
  strategy.mcx (Yahoo GC=F etc.)     ──► mcx_calls   [NO expectancy gate]

API
  /api/consultant/{swing,intraday,index,mcx}
  /api/signals/*, /api/weekly-picks, /api/backtest, /api/expectancy/*
  /api/kotak/*, /api/kotak/option-chain/*, /api/chart/*
  /api/health (liveness) vs /api/health/ready (EOD FRESH + Kotak configured + non-demo)

UI (CRA)
  App.js desks: Swing | Intraday | Index | MCX
  SignalBoard (badge + expectancy strip), ChartWorkstation, OptionChainPanel, MarketSessionBanner
```

**Persistence (verified in `store.py` schema):** `eod`, `indicators`, `screener_results`, `expectancy_metrics`.  
**No table for persistent 5-minute bars** — 5m series exist only in-memory on `LiveQuote.closes_5m` / Yahoo chart fetch / Kotak bar aggregator memory.

### 0.3 Claimed vs verified behavior

| Claim (guide / prior report / version string) | Verified behavior | Evidence | Confidence |
|-----------------------------------------------|-------------------|----------|------------|
| Version / phase “v4” in README | Code is `5.0.0-phase5` | `main.py` `APP_VERSION` | High |
| Demo forbidden | `allow_demo_data=False` hard; demo adapter raises; `seed_demo_data.py` exits 1; demo signals 410 | `config.py`, `adapters/registry.py`, `seed_demo_data.py`, `test_mvp_platform.py` | High |
| Swing prices are EOD | Weekly picks use DB `eod`/`indicators`; `price_kind=eod_close` on `EODBar` | `market_types.py`, `weekly_swing.py`, PERSONAL_USE | High |
| Intraday is Yahoo 5m research tape | Default path `live_quotes.quote_snapshot` → Yahoo unless Kotak WS connected+subscribed | `live_quotes.py` `_kotak_quote_if_live` then `_fetch_chart` `source="yahoo_chart"` | High |
| Kotak WS optional | Prefer Kotak only if hub `ws.connected` and quote present; else Yahoo | `live_quotes.py` L85–109 | High |
| 5s stale freeze | `LIVE_QUOTE_STALE_SEC` default 5; `assess_quote_age` → STALE; `freeze_live_sides` flips BUY/SELL→HOLD | `config.py`, `market_session.py`, `intraday.py` / `index_desk.py` | High |
| Stale values still shown | Freeze changes **side** to HOLD/FLAT and tags `FEED_HALT`; LTP/price fields can remain on payload | `freeze_live_sides` | High — risk for Phase 1 |
| Yahoo labeled as broker live | `source` field is `yahoo_chart` or Kotak; `provenance` maps LIVE→`"live"` even for Yahoo | `LiveQuote.to_dict` provenance mapping | High — Phase 1 issue |
| Index strategy `index_mtf_vwap_v1` | Present in `index_desk.py` + sources on calls | `index_desk.py`, `index_calls.py` | High |
| PERSONAL_USE: “no PCR in this build” | Option chain / PCR / OI modules + `OptionChainPanel` exist; inactive until Kotak session+chain | `app/kotak/option_chain.py`, `routers/option_chain.py` | High — doc lag |
| Phase 5 STRONG uses same 5m rules | Index/intraday harness explicitly `proxy: True` daily OHLCV rules; swing uses real weekly picks | `expectancy/harness.py` `RULE_META`, honesty strings | High |
| UI shows proxy limitation on STRONG | Expectancy strip shows Win%/E/PF/N; does **not** surface `proxy` / honesty flag | `SignalBoard.js` `ExpectancyStrip` | High |
| 5m history persisted | Not in SQLite; only ephemeral quote fields | `store.py` schema | High |
| Scheduled EOD ingest | `run_daily_ingest.py` exists; no cron/systemd/APScheduler in repo; `start.sh` does not schedule | glob + `start.sh` | High |
| NSE holiday calendar | Weekday-only session clock; comment “no special holiday calendar” | `market_session.py` L19–41 | High |
| MCX = MCX INR contracts | Yahoo global futures (`GC=F`, …) + `mcx_hint`; units USD; docstring admits proxy | `strategy/mcx.py` | High |
| MCX desk works | **Baseline failure:** `build_mcx_desk` passes `LiveQuote` into `_bias` which calls `.get` → `AttributeError` → HTTP 500 | TestClient + `test_production_suite` against live API | High |
| Auth off personal default | `AUTH_ENABLED` default false | `config.py`, `.env.example` | High |
| `start.sh` matches Phase 1 | Still seeds demo path, prints demo logins, binds `0.0.0.0` | `start.sh` | High — contradiction |
| CI covers Phase 5 | CI runs phase1–4 + methodology/mvp/analyze; **omits** `test_phase5_expectancy.py` | `.github/workflows/ci.yml` | High |
| README “demo seed until live” | Obsolete vs Phase 1 refusal | `README.md` L62–80 | High |

### 0.4 Provider / fallback matrix

| Desk | Primary source | Timeframe | Persistence | Refresh | Freshness rule |
|------|----------------|-----------|-------------|---------|----------------|
| Swing | Kotak EOD (+ NSE bhav / Yahoo EOD fallbacks in ingest) | Daily | SQLite `eod`/`indicators` | Manual Refresh / Force full / `run_daily_ingest.py` | `store.freshness`: FRESH ≤1d vs last weekday; STALE > `MAX_DATA_AGE_DAYS` (default 3). Ready needs FRESH + Kotak configured + non-demo |
| Intraday | Kotak WS LTP if connected else **Yahoo 5m chart** | 5m bars in-memory + LTP | None for 5m | Poll (~15s desk) | Session IST 09:15–15:30; age > `LIVE_QUOTE_STALE_SEC` (5) → STALE + freeze sides |
| Index | Same live path for `^NSEI`/`^NSEBANK` + local NIFTY EOD regime | Daily regime + 5m structure | EOD only for NIFTY | Poll (~20s) | Same stale/session freeze as intraday |
| MCX | Yahoo futures (`GC=F` etc.) | Chart/LTP snapshot | None | Poll | Same LiveQuote age; desk currently 500s (type bug) |
| Charts | Yahoo intervals + optional Kotak bars when hub has them | 1m–1d | None durable | On demand | Source string on payload |
| Option chain | Kotak F&O tokens via WS | Snapshot | Process memory | Activate via API/UI | Requires authenticated session |

### 0.5 Strategy map

| Desk / rule ID | Inputs | Rules (summary) | Risk / expectancy |
|----------------|--------|-----------------|-------------------|
| Swing / `elite_momentum` | EOD+indicators, NIFTY regime | SMA regime gate; liquidity; breakout/pullback; vol/RS/score≥65; ATR stops | Shared `generate_weekly_picks` with classic backtest; Phase 5 walk-forward on same path; STRONG gated N≥30, E>0.25R, PF≥1.2 |
| Intraday / live bias | LiveQuote LTP + closes_5m | Day change, vs open, range, mom, RSI, VWAP if volume, ORB-lite; score≥62 LONG / ≤38 SHORT | Consultant grade + session discount; expectancy on **daily proxy** `intraday_bias_v1`, not 5m rules |
| Index / `index_mtf_vwap_v1` | Daily regime + 5m EMA9/21, VWAP, RSI, BN–Nifty; optional PCR | Score bands → BUY/SELL/HOLD | Expectancy on **daily EMA/RSI proxy**, labeled `proxy=true` in harness meta only |
| MCX | Yahoo futures change/range/mom | Heuristic LONG/SHORT/FLAT; ~0.8% stop/target on USD proxy | No expectancy gate; broken at runtime (LiveQuote vs dict) |

### 0.6 Security / operations review

| Area | Finding | Evidence |
|------|---------|----------|
| Bind | `start.sh` / docker-compose: `0.0.0.0:8000` | `start.sh`, `docker-compose.yml` |
| Auth | Default off; personal-desk OK if local-only | `config.auth_enabled` |
| CORS | Default `*` when `CORS_ORIGINS` empty | `config.cors_origin_list` |
| API docs | Default `ENABLE_API_DOCS=true` | `.env.example` |
| API key | Optional; only some mutators (`ingest`, `backtest`, kotak login, journal) | `security.py` |
| Secrets | `.env` gitignored; example has placeholders; Fernet vault for LLM keys | `.gitignore`, `llm_vault` |
| Default `SECRET_KEY` | Dev placeholder if unset | `config.py` |
| DB | SQLite `swing_trader.db`; no backup script in repo | `data/` |
| Startup contradiction | `start.sh` still tries demo seed + prints demo passwords though seed refuses | `start.sh` vs `seed_demo_data.py` |
| CI | Phase 5 tests not in workflow | `ci.yml` |
| Holidays | Not modeled | `market_session.py` |
| Multi-instance | Feed hub / quote cache process-local | `kotak/feed_hub.py`, `live_quotes.py` |

### 0.7 Baseline test / build results (2026-10-26)

**Commands and results (no feature changes made this phase):**

```text
# Backend — CI-equivalent + Phase 5 (AUTH_ENABLED=false, MARKET_DATA_ADAPTER=live)
python -c "…methodology…"                         → OK
python test_methodology.py                         → 8 OK
python test_phase1_market.py                       → 9 OK
python test_phase2_kotak_feed.py                   → 9 OK
python test_phase3_option_chain.py                 → 8 OK
python test_phase4_chart.py                        → 3 OK
python test_phase5_expectancy.py                   → 14 OK  (**not in CI**)
python test_crypto_adapters.py                     → 4 OK
python test_mvp_platform.py                        → 4 OK
python test_analyze_validation.py                  → 9 OK

# Frontend
CI=true npm test -- --watchAll=false               → 3 suites / 10 tests PASS
npm run build                                      → Compiled successfully

# Extra (not CI)
python test_api_suite.py                           → OK (against local DB / optional live)
python test_world_class.py                         → 6/6 PASS (required live API)
python test_production_suite.py                    → FAIL 3/16
  - GET /api/mcx/signals 500
  - GET /api/consultant/mcx 500
  - GET /api/consultant/daily 500 (likely depends on MCX)
Root cause (TestClient): AttributeError LiveQuote has no .get in strategy/mcx.py:_bias
```

**Baseline failures to preserve (do not silently blame later phases):**
1. MCX / consultant daily HTTP 500 — LiveQuote dataclass vs dict API in `strategy/mcx.py`.
2. CI gap — `test_phase5_expectancy.py` not executed in GitHub Actions.
3. Doc / `start.sh` / README contradictions vs Phase 1 live-only reality.

### 0.8 Prioritized gap list (feeds Phase 1–7)

1. **P0/P1 — Label honesty:** Yahoo LTP can get `provenance=live`; UI “LIVE” without “Yahoo research / fallback” when Kotak down. Stale freeze keeps prices while flipping sides — risk of looking “current.”
2. **P0 bug — MCX 500** — type contract break after LiveQuote (fix in Phase 5 or early hotfix with approval).
3. **P3 — No persistent 5m store** — expectancy for index/intraday cannot equal live rules until bars persist.
4. **P3 — Proxy STRONG gates** — daily proxies can unlock STRONG for desks whose live rules differ; UI does not show `proxy`.
5. **P4 — No holiday-aware scheduled ingest** — Swing freshness is operator-manual.
6. **P2 — Kotak WS opt-in** — real path exists (`app/kotak/*`) but credentials/session required; untested end-to-end without live login in this audit.
7. **P5 — MCX proxy semantics** — USD futures ≠ MCX INR lots; no expectancy by design today.
8. **P7 — Ops** — `0.0.0.0`, CORS `*`, docs on, start.sh demo messaging, CI incomplete, SQLite backup absent.
9. **P6 — Charts/options** — Implemented but Yahoo-heavy / Kotak opt-in; PERSONAL_USE outdated on PCR.

### 0.9 Proposed implementation sequence

The prescribed Phase 1→7 order remains appropriate. One optional deviation:

- **Suggested micro-fix before or at start of Phase 5:** MCX `LiveQuote`/dict normalization (baseline 500). Prefer fixing under Phase 5 (MCX correctness) unless you approve a tiny Phase 1-adjacent hotfix so other desks aren’t blocked by daily smoke failures.

Phase 3 should **disable or downgrade STRONG** for index/intraday until 5m history + shared rule code exist — do not expand daily-proxy gates.

### 0.10 Decisions / assumptions / risks

| Item | Note |
|------|------|
| Assumption | Local `.env` has Kotak consumer key configured (boolean present); TOTP/WS session **not** verified live in this audit |
| Assumption | `test_world_class` / `test_production_suite` hit a reachable API on localhost during baseline; unit suites do not require it |
| Risk | Large uncommitted working tree (Phases 1–5 local work) vs `origin/main` last commit “v4” — upgrade work continues on dirty tree |
| Risk | Dual cost models: classic `ROUND_TRIP_COST` ~15 bps vs Phase 5 India leg costs |
| Out of scope Phase 0 | No feature code changes; only this tracker |

### 0.11 Files inspected (non-exhaustive)

`backend/app/main.py`, `config.py`, `live_quotes.py`, `market_session.py`, `market_types.py`, `store.py`, `security.py`, `adapters/registry.py`, `strategy/{weekly_swing,intraday,index_desk,mcx,backtest}.py`, `signals/*_calls.py`, `expectancy/*`, `kotak/*` (presence), `routers/{backtest,market,kotak_feed,option_chain}.py`, `seed_demo_data.py`, `start.sh`, `docker-compose.yml`, `.github/workflows/ci.yml`, `README.md`, `docs/PERSONAL_USE.md`, `.env.example`, `frontend/src/{App.js,components/SignalBoard.js,ProvenanceBadge.js,IntradayDesk.js,IndexDesk.js}`

---

## Commands log (Phase 0)

| Command | Result |
|---------|--------|
| `git status -sb` / `git log -5` | Dirty tree on `main`; HEAD `92e3bac` frontend CI fix; many Phase1–5 local mods uncommitted |
| Backend unittest suite (listed above) | All listed CI+phase5 suites **PASS** |
| Frontend test + build | **PASS** |
| `test_production_suite.py` | **FAIL** 3 (MCX/daily 500) |
| TestClient MCX | Confirmed `AttributeError: 'LiveQuote' object has no attribute 'get'` |

---

## Tests added this phase (Phase 0)

None (audit only).

---

## Phase 1 — Truthful market-data contracts (COMPLETE)

### Pre-edit summary (from Phase 0, relevant)

- Yahoo age-fresh quotes could map `provenance=live` while `source=yahoo_chart`.
- Stale freeze flipped sides to HOLD but left prices looking like current live edge.
- Session clock was weekday-only with `HOLIDAY` mislabel for weekends; no NSE holiday calendar (deferred to Phase 4).
- `/api/health` vs `/api/health/ready` existed but needed explicit liveness vs EOD readiness wording.
- MCX LiveQuote `.get` bug left for Phase 5 (not in this phase).

### Files changed

| Area | Paths |
|------|--------|
| Contracts | `backend/app/market_types.py`, `backend/app/market_session.py` |
| Quotes | `backend/app/live_quotes.py` |
| Desks | `backend/app/strategy/intraday.py`, `backend/app/strategy/index_desk.py` |
| API | `backend/app/main.py`, `backend/app/routers/market.py` |
| UI | `frontend/src/components/{ProvenanceBadge,MarketSessionBanner,SignalBoard,IntradayDesk,IndexDesk}.js`, `App.css` |
| Tests | `backend/test_phase1_market.py`, `backend/test_phase5_expectancy.py` (version assert), `frontend/.../SignalBoard.test.js` |
| Docs/ops honesty | `docs/PERSONAL_USE.md`, `start.sh` (demo seed messaging) |
| Tracker | `DESK_UPGRADE_TRACKER.md` |

### Behavior delivered

- States: `LIVE` (Kotak broker only), `FALLBACK` (Yahoo research), `STALE`, `EOD`, `UNAVAILABLE`/`ERROR`, `PRE_MARKET`/`POST_MARKET`/`WEEKEND` (+ `HOLIDAY` reserved).
- `LiveQuote.to_dict()` exposes `market_data_state`, `provenance`, `provider_class`, `is_current_live`, `is_last_observation`, quote + ingestion timestamps.
- `freeze_live_sides` tags `LAST_OBSERVATION`, clears STRONG/BUY badges, caps confidence, sets `signal_generation=halted`.
- Desk banners/cards show FALLBACK vs BROKER LIVE vs STALE last-obs.
- Calendar note explicit: holiday calendar **not** applied (`holiday_calendar_applied: false`).

### Commands / results (Phase 1)

```text
python test_phase1_market.py -v     → 16 OK
python test_phase2_kotak_feed.py    → 9 OK
python test_phase3_option_chain.py  → 8 OK
python test_phase4_chart.py         → 3 OK
python test_phase5_expectancy.py    → 14 OK
python test_mvp_platform.py         → 4 OK
python test_methodology.py          → 8 OK
python test_crypto_adapters.py      → 4 OK
python test_analyze_validation.py   → 9 OK
CI=true npm test -- --watchAll=false → 12 PASS
npm run build                       → OK
```

### Assumptions / remaining risks

- Phase 0 MCX 500 bug **unchanged** (out of Phase 1 scope).
- Yahoo FALLBACK may still generate research BUY/SELL when age-fresh (explicitly labeled; not broker LIVE).
- NSE holidays still look like REGULAR weekdays until Phase 4.
- Phase 2 still required for full Kotak reconnect/lifecycle hardening.
- README root still partially outdated (v4 wording) — not fully rewritten this phase; PERSONAL_USE updated.

### Phase 0 assumptions disproved?

None material. Confirmed Yahoo→live provenance issue and stale observation risk; fixed as designed. Weekend label corrected from HOLIDAY→WEEKEND (clarification, not disproof).

### Next steps (awaiting approval)

**Phase 2** — Broker live-feed path and explicit fallback behavior (Kotak WS lifecycle, no silent Yahoo-as-broker).

---

## Phase 2 — Broker live-feed path and explicit fallback (COMPLETE)

### Verified Kotak interface (repo + official guide alignment)

| Item | Finding | Confidence |
|------|---------|------------|
| Protocol in use | HS / `apifeed` WebSocket with JSON auth then little-endian **`native_batch`** binary (`app/kotak/ws_client.py`, `protocol.py`) | High (matches Kotak Market Data WebSocket Developer Guide pattern used in-repo) |
| Default feed URL | `wss://sfeed.kotaksecurities.com/apifeed` (`session.py`) | High (code default; live host not probed this phase) |
| Auth | Session login (TOTP path) → WS frame `user`/`auth`/`format=native_batch` | High (code); **live login not executed** this phase |
| Subscribe intents | `subscribeScrips`, `subscribeScripsLite`, `subscribeDepth`, `subscribeIndices` (+ unsubscribe twins) | High (code constants); **not live-verified** |
| Reconnect | Exponential backoff to `max_backoff_sec` (60); **auth failures are fatal** (no credential-spam reconnect) | High (unit/status); live reconnect not exercised |
| SFeed migration | Kotak announced SFeed migration deadline **15 Sep 2026** — desk has **not** rewritten for SFeed | High (documented; no SFeed client) |
| What we do **not** claim | Tick stream SLA, L2 depth correctness, or F&O coverage as live-verified | Explicit in `provider_policy` / `coverage_claims` |

**Could not verify without interactive TOTP/session credentials:** end-to-end connect → auth → subscribe → LTP update against the real Kotak host. Local `.env` has `KOTAK_CONSUMER_KEY` (EOD historical) but no live WS session was established in this phase.

### Files changed (Phase 2)

| Area | Paths |
|------|--------|
| Provider boundary | `backend/app/providers/live_quote_provider.py`, `providers/__init__.py` |
| Tick / secrets | `backend/app/kotak/tick_guard.py` |
| WS / hub | `backend/app/kotak/ws_client.py`, `feed_hub.py`, `protocol.py` (header honesty) |
| Quotes / adapter | `backend/app/live_quotes.py`, `adapters/live_yahoo.py` |
| Config | `backend/app/config.py`, `backend/.env.example` (`ALLOW_YAHOO_LTP_FALLBACK`) |
| API / health | `backend/app/main.py`, `routers/kotak_feed.py` |
| UI | `frontend/src/App.js`, `services/api.js` |
| Tests / CI | `backend/test_phase2_provider.py`, `test_crypto_adapters.py`, `test_phase5_expectancy.py`, `.github/workflows/ci.yml` |
| Docs | `docs/PERSONAL_USE.md`, `DESK_UPGRADE_TRACKER.md` |

### Behavior delivered

- Resolution order: Kotak hub quote when WS connected+cached → else Yahoo 5m **only if** `ALLOW_YAHOO_LTP_FALLBACK=true` → else honest UNAVAILABLE/ERROR (no demo).
- Yahoo always `market_data_state=FALLBACK` / provenance fallback — never broker LIVE.
- Hub drops out-of-order ticks (`should_accept_tick`); counters on feed status.
- Auth-fail sets `fatal_auth` and stops reconnect loop; errors sanitized before log/API.
- `GET /api/kotak/feed/status` + `/api/health` expose WS health, protocol id, Yahoo fallback flag, and **non-claims** for depth/F&O/e2e.
- UI WS chip: LIVE vs off; Yahoo fallback labeled explicitly when off.

### Commands / results (Phase 2)

```text
python test_phase2_provider.py          → 15 OK
python test_phase2_kotak_feed.py        → 9 OK
python test_phase1_market.py            → 16 OK
python test_phase3_option_chain.py      → 8 OK
python test_phase4_chart.py             → 3 OK
python test_phase5_expectancy.py        → 14 OK
python test_methodology.py              → 8 OK
python test_crypto_adapters.py          → 4 OK
python test_mvp_platform.py             → 4 OK
python test_analyze_validation.py       → 9 OK
CI=true npm test -- --watchAll=false    → 12 PASS
npm run build                           → OK
```

**Not run / not claimed:** live Kotak TOTP login + WS e2e; production_suite MCX 500 (Phase 0 baseline, deferred to Phase 5).

### Assumptions / remaining risks

- SFeed deadline approaches — HS/apifeed client may need a future migration phase (not Phase 2).
- Depth/F&O subscribe code exists but is **not** live-verified; UI/API say so.
- Yahoo FALLBACK still usable for research signals when age-fresh (labeled).
- MCX 500 and Phase 3 5m persistence remain open.
- Root README may still lag version wording.

### Phase 0–1 assumptions disproved?

None material. Confirmed prefer-Kotak-else-Yahoo path; made Yahoo opt-out via config and isolated behind provider boundary.

### Next steps (awaiting approval)

**Phase 3** — Persistent 5m history and strategy-valid expectancy (no daily-proxy STRONG expansion).

---

## Phase 3 — Persistent 5m history + valid expectancy (COMPLETE)

### Rules traced (before change)

| Desk | Live rule | Inputs | Prior expectancy gap |
|------|-----------|--------|----------------------|
| Intraday | `intraday_bias_v1` via `score_intraday_bias` / `_signal_for` | LTP + `closes_5m`/`volumes_5m`, session OHLC, day change; VWAP/ORB/RSI/mom | Daily ROC/SMA **proxy** gated STRONG |
| Index | `index_mtf_vwap_v1` via `score_index_mtf` / `_score_index` | Prior-day SMA regime + 5m EMA9/21, VWAP, RSI, slope, BN spread | Daily EMA/RSI **proxy** gated STRONG |

Shared cores extracted: `strategy/intraday_core.py`, `strategy/index_core.py` (live + harness).

### 5m persistence contract

| Concern | Behavior |
|---------|----------|
| Schema | SQLite `bars_5m` (same DB file): symbol, bar_start_unix, session_date, OHLCV, source, completed |
| Dedup | PK `(symbol, bar_start_unix)`; incomplete never overwrites completed; higher source priority wins |
| Session | Weekday IST 09:15–15:25 bar starts; weekends rejected; holidays still not calendared (Phase 4) |
| Incomplete | Forming Yahoo/Kotak bucket dropped from strategy store |
| Gaps | `find_gaps(session_date, present)` vs expected 5m grid |
| Retention | `BARS_5M_RETENTION_DAYS` (default 45) purge |
| Restart | WAL upserts idempotent |
| Ingest | Yahoo chart persist on quote fetch; Kotak closed 5m from feed hub |

### Expectancy / gates

- Daily proxy runners **removed**.
- Walk-forward uses shared 5m cores; fill at **next bar open**; India MIS costs + slippage.
- Hold in 5m bars (intraday 12 / index 24).
- Meta records: strategy_id/version, timeframe, interval, costs, run_at, source, `proven=false`.
- Insufficient 5m → `insufficient_history`, STRONG blocked (`INSUFFICIENT_5M_HISTORY`); UI shows “5m hist insufficient”.
- Disclaimer: gate pass ≠ proven/profitable.

### Files changed (Phase 3)

| Area | Paths |
|------|--------|
| Bars | `backend/app/bars_5m.py` |
| Cores | `strategy/intraday_core.py`, `index_core.py`; wired into `intraday.py`, `index_desk.py` |
| Harness | `expectancy/harness_5m.py`, `harness.py`, `gate.py` |
| Ingest | `live_quotes.py`, `kotak/feed_hub.py` |
| Config/API/UI | `config.py`, `main.py`, `routers/backtest.py`, `SignalBoard.js`, `App.css` |
| Tests/CI/docs | `test_phase3_bars.py`, phase2/5 asserts, `ci.yml`, `PERSONAL_USE.md`, tracker, `.env.example` |

### Commands / results (Phase 3)

```text
python test_phase3_bars.py              → 14 OK
python test_phase1_market.py            → 16 OK
python test_phase2_kotak_feed.py        → 9 OK
python test_phase2_provider.py          → 15 OK
python test_phase3_option_chain.py      → 8 OK
python test_phase4_chart.py             → 3 OK
python test_phase5_expectancy.py        → 14 OK
python test_methodology.py              → 8 OK
python test_crypto_adapters.py          → 4 OK
python test_mvp_platform.py             → 4 OK
python test_analyze_validation.py       → 9 OK
CI=true npm test -- --watchAll=false    → 12 PASS
npm run build                           → OK
```

### Limitations

- Yahoo default range `5d` — limited sample until more sessions accumulate or range widened.
- NSE holiday calendar still absent (Phase 4) — weekend filter only.
- Kotak→`closes_5m` on LiveQuote still thin if WS has LTP without enough closed bars in store.
- MCX 500 baseline unchanged (Phase 5).
- Multi-year 5m archive not claimed; retention is short-window research history.

### Next steps (awaiting approval)

**Phase 4** — Scheduled, holiday-aware EOD ingestion.

---

## Phase 4 — Scheduled, holiday-aware Swing EOD (COMPLETE)

### Calendar approach (honest)

| Item | Finding |
|------|---------|
| Live NSE holiday API | **Not used** — no verified official machine API in repo |
| Interface | `app/nse_calendar.py` + configurable `app/data/nse_holidays.json` + `NSE_EXTRA_HOLIDAYS` |
| Weekends | Always closed |
| Holidays | Operator-maintained snapshot (public NSE circulars); some 2026 rows marked tentative |
| Limitation surfaced | `holiday_list_complete`, `limitation` on API/session; UI schedule chip |

### Scheduling

- Daemon thread on API startup when `EOD_INGEST_SCHEDULE_ENABLED=true` (default).
- Default fire **18:45 IST** after settle **18:30 IST**.
- Skips weekends/holidays; skips if journal already has success for `expected_eod_as_of`.
- Restart-safe: decision uses journal + clock (no in-memory-only “already ran”).
- Manual Refresh / Force full unchanged (`trigger=manual`).

### Freshness / readiness

- `Database.freshness` ages in **trading days** vs `expected_eod_as_of` (settle-aware).
- Swing / `/api/health/ready` still require FRESH (now holiday-aware).
- Ingest journal: provider, range, target session, rows, errors, last success.

### Files

| Area | Paths |
|------|--------|
| Calendar | `nse_calendar.py`, `data/nse_holidays.json` |
| Journal / schedule | `ingest_journal.py`, `ingest_scheduler.py` |
| Freshness / session | `store.py`, `market_session.py`, `ingest.py` (gap fill) |
| Pipeline / API | `pipeline.py`, `routers/ingest.py`, `main.py`, `run_daily_ingest.py` |
| Config/UI/docs | `config.py`, `.env.example`, `App.js`, `api.js`, `PERSONAL_USE.md`, CI, tests |

### Commands / results (Phase 4)

```text
python test_phase4_eod.py               → 14 OK
(+ phase1–5 / methodology / crypto / mvp / analyze) → all PASS
CI=true npm test -- --watchAll=false    → 12 PASS
npm run build                           → OK
```

Unit tests use **fixed IST datetimes** (not “today”).

### Limitations

- Holiday JSON is **not** auto-synced from NSE — verify circulars; use `NSE_EXTRA_HOLIDAYS` for ad-hoc closures.
- Tentative 2026 religious dates need operator confirmation.
- Scheduler is in-process (dies with API process); no separate cron/systemd unit shipped.
- MCX LiveQuote crash fixed in Phase 5 (see below).

---

## Phase 5 — COMPLETE (MCX correctness / proxy honesty)

### Goal

Audit every commodities mapping; distinguish Yahoo global futures proxy from exchange-listed MCX INR; never imply INR contract/lot mapping; constrain confidence; skip expectancy unless justified; research-only.

### Audit summary (feed reality)

| Desk id | Yahoo | Class | Currency / unit | MCX listed? | Mapping status |
|---------|-------|-------|-----------------|-------------|----------------|
| GOLD | `GC=F` | global_futures_proxy | USD / troy oz | **No** | `unvalidated_name_hint` (GOLD/GOLDM) |
| SILVER | `SI=F` | global_futures_proxy | USD / troy oz | **No** | hint SILVER/SILVERM |
| CRUDE | `CL=F` | global_futures_proxy | USD / barrel | **No** | hint CRUDEOIL* |
| NATGAS | `NG=F` | global_futures_proxy | USD / mmBtu | **No** | hint NATURALGAS |
| COPPER | `HG=F` | global_futures_proxy | USD / lb | **No** | hint COPPER |
| USDINR | `INR=X` | fx_context | INR per USD | **No** | FX context only |

- Provider: Yahoo chart continuous series — **not** MCX tickers, lots, ticks, or dated expiries.
- Hours: near-24h US futures / FX — **not** MCX INR session (~09:00–23:30 IST with breaks; verify exchange).
- Roll: continuous Yahoo roll ≠ MCX front-month; basis can diverge.
- Price scale: `1.0` as Yahoo LTP (no INR conversion / lot scaling in app).

### Expectancy gate decision

**Not enabled** for this desk. Justification missing: no verified MCX INR series, no India commodity cost model, continuous USD proxy ≠ MCX contract, sample would be mis-specified. Desk returns `expectancy_gated: false`, explicit `proxy_desk_no_expectancy`, confidence cap **≤58**, no `STRONG_*` badges.

### Delivered

| Area | Change |
|------|--------|
| Registry | `strategy/mcx_instruments.py` — class, currency, unit, scale, hours/expiry/roll notes, lot_sizing unavailable |
| Strategy | `strategy/mcx.py` — `_snap_to_dict` fixes LiveQuote AttributeError; proxy tags; unavailable labels |
| Calls / grade | `mcx_calls.py`, `grade_mcx` — conf cap, no STRONG, expectancy block |
| API | `GET /api/consultant/mcx/instruments` catalog; desk payload honesty fields |
| UI | McxDesk / App hero / SignalBoard proxy labels + currency·unit hints |
| Tests | `test_phase5_mcx.py` (12); CI includes it |
| Version | `5.5.0-upgrade-p5` |

### Commands / results (Phase 5)

```text
python test_phase5_mcx.py                 → 12 OK
CI-equivalent backend suite (methodology + phase1–5 + crypto/mvp/analyze) → all PASS
CI=true npm test -- --watchAll=false      → 12 PASS
npm run build                             → OK (pre-existing eslint self-assign warning in MarketSessionBanner)
```

### Limitations

- Still **no** exchange-listed MCX INR feed, contract codes, lots, margins, or roll calendar.
- `related_mcx_symbols` are **name hints only** — not validated 1:1 mappings.
- USD commodity moves ≠ INR MCX P&L (FX + basis + lot size omitted by design).
- Expectancy / STRONG remain off until a verified MCX series + costs exist.
- Research-only: no order instructions or contract sizing.

### Next steps (awaiting approval)

**Phase 6** — Charts, optional depth/options, polish. → **COMPLETE** (see below)

---

## Phase 6 — COMPLETE (chart correctness + optional depth/options honesty)

### Audit (pre-change)

| Path | Finding |
|------|---------|
| `chart_data.build_chart_payload` | Yahoo + EOD OHLCV; indicators from same bars; missing Yahoo stamps skipped silently (no count) |
| Daily Yahoo dates | Converted with **UTC** → possible IST day-shift |
| Payload | Source string only; weak freshness/TZ/status; walls/OI could appear empty without “unavailable” |
| UI `ChartWorkstation` | Loading/error thin; walls toggled without availability gate |
| L2 `GET .../feed/depth/{key}` | Empty book returned as `bids: []` (looks like thin book, not unavailable) |
| Option chain | Optional + activate path exists; idle 404 — docs lagged; status lacked explicit unavailable envelope |
| Strategy vs chart | EMA algorithm matched `index_core.ema`; RSI formulas differ (Wilder vs simple) — must document, not fake-equal |

### Verified (shipped)

| Feature | Verified how |
|---------|----------------|
| OHLCV + interval/range echo | Payload `bars`, `interval`, `range` (limit, yahoo_interval/range, returned_bars) |
| IST timezone labels | Daily bars use IST calendar date; `timezone.display_timezone=Asia/Kolkata`; intraday unix + `last_bar_ist` |
| Missing bars | Counted `missing_bars_skipped`; never fill-forward |
| Indicators from chart OHLCV | EMA/VWAP/RSI/MACD from returned bars only |
| EMA ↔ strategy | Unit test: chart `ema_ribbon` last = `index_core.ema` on same closes |
| Source / freshness / price_kind | `source`, `freshness.{status,label,age_sec}`, `price_kind` (eod_close / yahoo_daily_close / intraday_bar_close) |
| UI states | LOADING / OK / AGING / STALE / UNAVAILABLE + alert/status roles; walls/OI gated |
| Option chain idle | Status `available:false`; UI “Unavailable” banner (not zero PCR) |
| Depth without book | `available:false`, `bids/asks: null` — not empty arrays as market data |

### Unavailable / not claimed

| Feature | Why |
|---------|-----|
| L2 depth as live-verified | Subscribe path exists; **not** CI e2e verified — chart does not render L2 |
| PCR / walls / Greeks | Only when Kotak session + chain **activate**; otherwise unavailable |
| OI on chart | Only if Kotak WS bar merge supplies `oi` |
| Chart RSI = desk RSI | Same closes; **different formula** (Wilder vs simple) — documented in `indicators_note` |
| Broker tick LTP on chart | Default `ltp` = last bar close; Kotak LTP only on `/live` when WS quote present (`ltp_source`) |

### Delivered paths

`chart_data.py`, `routers/stocks.py`, `routers/kotak_feed.py`, `routers/option_chain.py`, `ChartWorkstation.js` (+test), `OptionChainPanel.js`, `App.css`, `test_phase6_chart.py`, CI, `PERSONAL_USE.md`, version `5.6.0-upgrade-p6`.

### Commands / results (Phase 6)

```text
python test_phase6_chart.py             → 12 OK
CI-equivalent backend suite             → all PASS
CI=true npm test -- --watchAll=false    → 14 PASS (incl. ChartWorkstation)
npm run build                           → OK (pre-existing MarketSessionBanner eslint warning)
```

### Next steps

**Phase 7** → **COMPLETE** (see below). Upgrade Phases 0–7 finished for this personal desk.

---

## Phase 7 — COMPLETE (ops / security / CI / release honesty)

### Goal

Make local-only operation explicit with auth off; harden defaults against accidental public exposure; secret-safe health/logs; SQLite backup guidance; CI includes all phase tests; reconcile docs/start/env; **do not** claim production-ready without evidence.

### Delivered

| Area | Change |
|------|--------|
| Bind | `BIND_HOST` default `127.0.0.1`; `start.sh` loopback; boot **refuses** `0.0.0.0` + auth off unless `ALLOW_PUBLIC_BIND=true` |
| CORS | Empty `CORS_ORIGINS` → localhost list (**not** `*`) |
| Health | `security` posture + SQLite `schema` check; `production_ready_claim: false` |
| Secrets | Broader `sanitize_error_text` (api_key / consumer_key / totp / session); paths as basename in schema |
| Backup | `scripts/backup_sqlite.sh` + `docs/OPS.md` restore notes |
| Compose | Publish `127.0.0.1:8000/3000`; container `ALLOW_PUBLIC_BIND=true` for internal listen only |
| Docs | README / QUICKSTART / PERSONAL_USE / CTO_READINESS reconciled — no demo seed path |
| CI | `test_phase7_ops.py` + phases 1–7; `BIND_HOST` / `EOD_INGEST_SCHEDULE_ENABLED=false` |
| Version | `5.7.0-upgrade-p7` |

### Commands / results (Phase 7)

```text
python test_phase7_ops.py                 → 12 OK
CI-equivalent backend (methodology + p1–p7 + crypto/mvp/analyze) → all PASS
CI=true npm test -- --watchAll=false      → 14 PASS
npm run build                             → OK
assert_safe_boot loopback                 → OK
assert_safe_boot 0.0.0.0 auth-off         → RuntimeError (expected)
./scripts/backup_sqlite.sh                → OK when DB present
```

### Intentional limitations (not enterprise)

- No multi-instance feed stickiness, no K8s/HA, no secret manager, no Alembic, no pager/SLO stack.
- In-process EOD scheduler; holiday JSON operator-maintained.
- Kotak WS / L2 / option-chain e2e **not** verified in CI.
- MCX = global futures proxy; charts Yahoo/EOD-heavy.

### Release verdict (evidence-based)

**Suitable for personal local research use** with Kotak key + Force full + loopback bind.  
**Not production-ready** for public internet, paid multi-user SaaS, or unauthenticated LAN exposure.

**STOP — Phase 7 complete.** (Options OI viz added as approved follow-on — see below.)

---

## Options data + OI visualization — COMPLETE (approved follow-on)

### Verified capabilities this phase depends on

| Capability | Verified? | Evidence / limit |
|------------|-----------|------------------|
| Kotak scrip-master OPT expiries/strikes | Code path yes; needs loaded scrip | `list_expiries` / `option_chain_tokens` |
| Live CE/PE quotes + OI via Neo WS | Path exists after login+activate | **Not** CI e2e-verified (`provider_e2e_verified_in_ci: false`) |
| Session volume on quote | When feed sends it | Else field `available: false` |
| IV | Model-derived from LTP (Black-76/BS) | **Not** exchange IV — labeled in `field_semantics` |
| ΔOI | Session baseline vs first obs / prev_day_oi | **Not** guaranteed exchange DOI tape |
| Alternate options provider (Yahoo/NSE) | **Not used** | Idle = unavailable; no silent fallback |
| Multi-expiry live OI at once | **No** | Only activated expiry has OI; others listed as unavailable |

### Delivered

- `app/options_oi.py` — normalize + freshness + expiry comparison honesty
- `GET /api/kotak/option-chain/{u}/oi-viz`
- UI `OiComparisonChart` (call/put OI by strike + expiry table)
- Tests: `test_options_oi.py`, `OiComparisonChart.test.js`; CI wired
- Version `5.8.0-options-oi`

### Results (2026-10-26)

```text
python test_options_oi.py              → 10 OK
python test_phase3_option_chain.py     → 8 OK
python test_phase7_ops.py              → 12 OK
CI=true npm test -- --watchAll=false   → 16 PASS (incl. OiComparisonChart)
npm run build                          → OK
```

### Blockers / honesty

- Without Kotak session + activate: OI viz `available:false` with blocker text.
- Cross-expiry OI requires separate activate per expiry — not invented.
- OI/PCR explicitly **not** trade signals in API + UI disclaimer.
- Live Kotak WS options e2e remains **unverified in CI**.

**STOP — options OI viz phase complete.**

---

## Manual trade journal + capital accounting — COMPLETE (approved)

### Scope

User-entered trade & capital ledger (not broker reconciliation). Week Journal remains a lighter research log.

### Delivered

| Piece | Detail |
|-------|--------|
| Storage | SQLite `data/trade_ledger.db` — trades, exits, capital movements, audit |
| API | `/api/ledger/summary`, `/trades`, exits, capital movements, corrections, audit |
| Labels | `source_label=user_entered_not_broker_fill`; disclaimer on all payloads |
| P&L | Realized = exit gross − fees_total; unrealized only with reliable quote, **separate** from book equity |
| Capital | starting + deposits − withdrawals + realized → book_equity; fees as costs |
| Corrections | Soft-supersede + `ledger_audit` (reason required) |
| Privacy | Health/root do **not** embed trade rows; mutations gated by `API_KEY` when set |
| UI | `TradeLedger` on Swing desk |
| Version | `5.9.0-trade-journal` |

### Results (2026-10-26)

```text
python test_trade_ledger.py            → 11 OK
CI=true npm test -- --watchAll=false   → 17 PASS (incl. TradeLedger)
npm run build                          → OK
```

**STOP — trade journal phase complete; no further phase started.**

---

## Risk-based position sizing — COMPLETE (approved)

### Scope

Research fixed-fractional position size from user risk limits, entry/stop, costs, and **verified** instrument lot / multiplier. Not an order instruction; does not place trades. Missing/stale/unverified inputs → `available=false` with blockers (no fabricated size).

### Delivered

| Piece | Detail |
|-------|--------|
| Core | `app/position_sizing.py` — EQ / FUT / OPT; MCX proxy blocked |
| Caps | `max_position_pct`, `max_notional`, `max_lots`, total exposure, verified margin |
| Options | Long: premium (or stop on premium) × verified lot × multiplier; short: requires verified margin |
| API | `GET /api/position-sizing/meta`, `POST /api/position-sizing/calculate` |
| UI | `PositionSizer` on Swing desk — formula + assumptions next to result |
| Honesty | `is_order_instruction=false`; disclaimer on every payload |
| Version | `5.10.0-position-sizing` |
| CI | `test_position_sizing.py` added to workflow |

### Results (2026-10-26)

```text
python test_position_sizing.py         → 20 OK
CI=true npm test -- --watchAll=false   → 19 PASS (7 suites, incl. PositionSizer)
npm run build                          → OK
```

**STOP — position-sizing phase complete; no further phase started.**

---

## Market-events calendar — COMPLETE (approved)

### Scope

Identifiable-source market events only. Per event: source, event time + timezone, last update, status. Distinguish scheduled facts / reported outcomes from model commentary (none invented). No invented dates, forecasts, outcomes, or impact. Stale/unavailable feeds obvious. Licensing: no commercial economic-calendar scrape/license.

### Delivered

| Piece | Detail |
|-------|--------|
| Sources | NSE holiday snapshot (`nse_holidays.json`); operator `market_events.json` (empty until verified rows); optional Kotak scrip-master F&O expiries when cached |
| Core | `app/market_events.py` — TZ conversion, dedupe, changed-event flags, feed freshness |
| API | `GET /api/market-events`, `GET /api/market-events/meta` |
| UI | `MarketEventsCalendar` — feed status banners, source/time/TZ, content-kind labels |
| Honesty | `invented=false`; model commentary channel always null; incomplete rows skipped |
| Version | `5.11.0-market-events` |
| CI | `test_market_events.py` |

### Results (2026-10-26)

```text
python test_market_events.py           → 12 OK
CI=true npm test -- --watchAll=false   → 24 PASS (9 suites, incl. MarketEventsCalendar)
npm run build                          → OK
```

**STOP — market-events phase complete; no further phase started.**

---

## Strategy evaluation — COMPLETE (approved)

### Scope

Evaluate audit-confirmed strategies/data only. Walk-forward + OOS, India costs/slippage, sample-size gates, regime breakdowns, drawdown/risk, baselines. Bias checklist (look-ahead, survivorship, overfitting, multiple testing). Record version, source/TF, period, parameters, assumptions. Options put/call only when data **and** explicit testable rules exist — OI/PCR never directional. Never crown “best” or label proven/guaranteed.

### Available for evaluation (audit)

| Rule | Data | Status |
|------|------|--------|
| `elite_momentum` | EOD SQLite | Evaluable when ≥60 sessions |
| `intraday_bias_v1` | `bars_5m` | Evaluable when 5m history sufficient |
| `index_mtf_vwap_v1` | `bars_5m` | Evaluable when 5m history sufficient |
| MCX proxy | Yahoo USD | **Not evaluable** (no harness / lot) |
| Options put/call | Kotak chain optional | **Not evaluable** — no explicit testable rules; OI/PCR ≠ signal |

### Delivered

| Piece | Detail |
|-------|--------|
| Core | `app/strategy_evaluation.py` |
| API | `GET/POST /api/strategy-evaluation*` |
| UI | `StrategyEvaluation` — evidence, OOS, bias, baselines, limitations |
| Tests | Leakage fill, costs reduce R, sample gates, OOS split, options honesty, API |
| Version | `5.12.0-strategy-eval` |

### Evidence & limitations

- Fills = next-bar open (leakage test). Costs via `IndiaCostAssumptions`.
- Chronological IS/OOS by signal date; gate N≥30 / E>0.25R / PF≥1.2 research-only.
- Survivorship / overfitting / multiple-testing residual risks disclosed, not eliminated.
- Historical metrics ≠ future returns; `selects_best=false`, `proven=false`.

### Results (2026-10-26)

```text
python test_strategy_evaluation.py     → 9 OK
CI=true npm test -- --watchAll=false   → 25 PASS (10 suites, incl. StrategyEvaluation)
npm run build                          → OK
```

**STOP — strategy-evaluation phase complete; no further phase started.**

---

## Final reverse-engineering audit — 2026-10-26

Full matrix, baseline commands, and backlog: [`FINAL_REVERSE_ENGINEERING_AUDIT.md`](FINAL_REVERSE_ENGINEERING_AUDIT.md).

### Baseline (this session, before remediations)

- Backend: **6 modules FAIL** — all observed failures = brittle `APP_VERSION` pins (`test_phase2_provider`, `test_phase3_bars`, `test_phase4_eod`, `test_phase5_mcx`, `test_phase5_expectancy`, `test_phase6_chart`). Other listed modules OK.
- Frontend Jest: **25 PASS / 10 suites**. `npm run build`: **OK**.

### Remediation batch 1 — AUDIT-P0-001 **DONE** (approved)

**Issue:** STRONG path attached user-visible `EDGE_PROVEN` tag while `expectancy.proven=false` and docs forbid “proven” claims.  
**Fix:** Replace with `GATE_PASS_RESEARCH`; strip legacy `EDGE_PROVEN`; docstring honesty.  
**Files:** `backend/app/expectancy/gate.py`, `backend/test_phase5_expectancy.py`

### Results — batch 1 (ran)

```text
python -m unittest test_phase5_expectancy.TestGate -v
→ Ran 4 tests — OK
```

Acceptance for AUDIT-P0-001: **PASSED**.

---

### Remediation batch 2 — AUDIT-P0-002 **DONE** (await approval for next)

**Issue:** Six phase tests pinned `APP_VERSION` to early `5.x` minors / incomplete follow-on labels; failed on `5.12.0-strategy-eval`.  
**Fix:** Replace brittle OR-lists with `re.match(r"^5\.(\d+)\.", APP_VERSION)` and phase-specific **minor ≥ N** floors (keeps meaningful floor; accepts 5.12.x).  
**Files changed (this batch only):**
- `backend/test_phase2_provider.py` (minor ≥ 2)
- `backend/test_phase3_bars.py` (minor ≥ 3)
- `backend/test_phase4_eod.py` (minor ≥ 4)
- `backend/test_phase5_mcx.py` (minor ≥ 5)
- `backend/test_phase5_expectancy.py` (minor ≥ 5)
- `backend/test_phase6_chart.py` (minor ≥ 6)
- `DESK_UPGRADE_TRACKER.md` (this evidence)
- `FINAL_REVERSE_ENGINEERING_AUDIT.md` (batch-2 note)

### Results — batch 2 (ran)

Six previously failing modules:

```text
python -m unittest test_phase2_provider  → Ran 15 — OK
python -m unittest test_phase3_bars      → Ran 14 — OK
python -m unittest test_phase4_eod       → Ran 14 — OK
python -m unittest test_phase5_mcx       → Ran 12 — OK
python -m unittest test_phase5_expectancy→ Ran 14 — OK
python -m unittest test_phase6_chart     → Ran 12 — OK
```

CI-equivalent backend job (same modules + env as `.github/workflows/ci.yml` backend step):

```text
methodology_assert OK
20 unittest modules — all OK
TOTAL_TESTS=216 FAIL_MODULES=0
```

Acceptance for AUDIT-P0-002: **PASSED** (backend CI-equivalent green locally).  
Frontend CI job / remote `gh` Actions run: **not executed this batch** — not claimed green remotely.

---

### Remediation batch 3 — AUDIT-P0-LEDGER-001 **DONE**

**Issue:** Empty Signal ledger looked like a broken strategy; demo rows could confuse.  
**Fix:** `signal_availability` honesty codes; strip `data_mode=demo` from platform list; UI empty-state explanation; `seed_platform.py` REFUSED.  
**Evidence:** `test_signal_availability` (15 OK); SignalHistory / SignalBoard UI tests.

---

### Remediation batch 4 — AUDIT-P1-003 **DONE**

**Issue:** Index/Intraday expectancy honesty not visible enough.  
**Fix:** `ExpectancyHonestyBanner` on Index + Intraday desks; SignalBoard gate-strip behavior.  
**Evidence:** Jest desk/banner suites; `GATE_PASS_RESEARCH` / no `EDGE_PROVEN` reattach.

---

### Remediation batch 5 — AUDIT-P1-004 **DONE**

**Issue:** NSE holiday feed could read as current when operator `as_of` aged.  
**Fix:** `is_current` / `presented_as_current`; UI “STALE — not current”; **`as_of` left at `2026-01-15`** (no fake refresh).  
**Evidence:** `test_market_events` (13 OK) + MarketEventsCalendar Jest.

---

### Remediation batch 6 — AUDIT-P1-005 **DONE**

**Issue:** Strategy evaluate / GET harness not under API_KEY when set.  
**Fix:** Middleware gates POST evaluate + GET `run_harness=true`; empty key keeps local UI usable.  
**Version:** `5.12.4-api-key-evaluate`.  
**Evidence:** `test_strategy_evaluation` (11 OK).

---

## Post-remediation final audit — 2026-10-26 (this session)

**Commands / results (verify, not tracker claims):**

```text
# Backend CI-eq + test_signal_availability
TOTAL_TESTS=234  FAIL_MODULES=0

# Frontend
CI=true npm test -- --watchAll=false  → 14 suites / 36 tests PASS
npm run build                         → OK (~249.8 kB gzip main)

# Spotchecks
freeze STALE BUY→HOLD; annotate stale BUY→HOLD; holiday as_of=2026-01-15;
posture production_ready_claim=false; no secret values in posture → SPOTCHECKS_OK
```

| Area | Status |
|------|--------|
| Market-data truth / freeze | **PARTIAL** (unit VERIFIED; live Kotak E2E **BLOCKED**) |
| Expectancy / GATE_PASS_RESEARCH | **PARTIAL** (unit VERIFIED; no EDGE_PROVEN) |
| Signal availability / ledger | **PARTIAL** (honesty VERIFIED; ledger empty by design) |
| Holiday freshness labeling | **PARTIAL** (stale labeling VERIFIED; feed as_of aged) |
| API_KEY evaluate gate | **PARTIAL** (VERIFIED when key set; open when empty) |
| LLM server-snapshot explain | **NOT IMPLEMENTED** |
| Broker order execution | **NOT IMPLEMENTED** (correct) |
| Credentialed Kotak live e2e | **BLOCKED** |

**Mocks vs live:** All green results above = unittest/Jest/fixtures/TestClient. Live Yahoo/Kotak E2E not claimed.

**CI gap:** `test_signal_availability.py` still omitted from `.github/workflows/ci.yml` (local green).

**Uncommitted after this audit write:** `FINAL_REVERSE_ENGINEERING_AUDIT.md`, `DESK_UPGRADE_TRACKER.md` only (doc updates).

**Backlog (not started):** AUDIT-P0-LEDGER-002 (destructive demo delete — needs explicit OK); AUDIT-P2 live harness; optional LLM server-snapshot design; CI add `test_signal_availability`.

**STOP — final audit complete; no product fixes this pass.**
