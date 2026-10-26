# Final Reverse-Engineering Audit — Swing Desk (post-remediation)

**Repository:** `bse-chief-equity-analyst`  
**Git HEAD:** `86fd559835d29d508612d4f0d502208d4c87e8b7` on `main` (up to date with `origin/main`)  
**Working tree at audit start:** clean at HEAD below; **after this pass:** doc-only dirty (audit + tracker).  
**Code version (feature branch):** `5.12.5-signal-clarity` (`backend/app/main.py`)  
**Audit date:** 2026-10-26  
**Method:** Claims verified against **code + tests** — not tracker/UI alone.  
**Deployment claim:** Personal/local research desk — `production_ready_claim: false`.  
**Follow-on:** Signal-clarity + audit implementation on `feature/signal-clarity-and-audit-pass` (see tracker). Not merged; not production-ready.

---

## Git state

| Item | Value |
|------|--------|
| HEAD | `86fd559` — *Ship the personal research desk so stale holidays, unproven evaluations, and keyed evaluate calls stay explicit.* |
| Prior | `92e3bac` (v4-era CI frontend fix) |
| Product code dirty | **none** |
| Uncommitted (this audit write) | `FINAL_REVERSE_ENGINEERING_AUDIT.md`, `DESK_UPGRADE_TRACKER.md` |

---

## Test / build results (this session)

### Backend (CI-equivalent + extras)

**Commands:**

```text
cd backend
python -c "from app.signals.methodology import score_evidence; assert score_evidence({})['direction']=='none'"
# then unittest runner over modules below
```

| Module | Tests | Result |
|--------|------:|--------|
| `test_phase1_market` | 16 | OK |
| `test_phase2_kotak_feed` | 9 | OK |
| `test_phase2_provider` | 15 | OK |
| `test_phase3_bars` | 14 | OK |
| `test_phase3_option_chain` | 8 | OK |
| `test_phase4_eod` | 14 | OK |
| `test_phase4_chart` | 3 | OK |
| `test_phase5_mcx` | 12 | OK |
| `test_phase5_expectancy` | 14 | OK |
| `test_phase6_chart` | 12 | OK |
| `test_phase7_ops` | 12 | OK |
| `test_options_oi` | 10 | OK |
| `test_trade_ledger` | 11 | OK |
| `test_position_sizing` | 20 | OK |
| `test_market_events` | 13 | OK |
| `test_strategy_evaluation` | 11 | OK |
| `test_mvp_platform` | 4 | OK |
| `test_methodology` | 8 | OK |
| `test_analyze_validation` | 9 | OK |
| `test_crypto_adapters` | 4 | OK |
| `test_signal_availability` | 15 | OK *(not in GitHub Actions CI.yml)* |
| **TOTAL** | **234** | **FAIL_MODULES=0** |

Spot-checks this session: `freeze_live_sides` BUY→HOLD + `FEED_HALT`/`STALE` tags; `annotate_call_display` attaches honesty fields without inventing prices (side flip is freeze’s job); holiday `as_of==2026-01-15`; posture `production_ready_claim=false`; no secret material in posture blob → `SPOTCHECKS_OK`. Frontend: no embedded secrets (only UX copy for `KOTAK_CONSUMER_KEY`; ephemeral LLM key is user-typed state, cleared after send).

**Remaining test failures:** **none** in the suite above.

**CI gap:** `.github/workflows/ci.yml` runs the modules above **except** `test_signal_availability.py`. Local CI-eq green including that module; remote Actions would omit it until workflow updated (not changed this audit).

### Frontend

```text
cd frontend
CI=true npm test -- --watchAll=false
→ Test Suites: 14 passed; Tests: 36 passed

npm run build
→ Compiled successfully (main JS ~249.8 kB gzip)
```

**Remaining failures:** none.

### Mocks/fixtures vs live E2E

| Kind | What this session covers |
|------|---------------------------|
| **Mocks / fixtures / TestClient** | All unittest/Jest results above; controllable clocks (holidays, availability); patched LLM; temp SQLite |
| **Live E2E** | **Not claimed.** Kotak WS/option-chain LIVE, broker fills, and Yahoo outside sandbox **BLOCKED** without credentials/network. Yahoo 403 tunnel noise observed in one trade-ledger privacy probe (treated as fetch fail, not invented quote). |

---

## Feature status matrix (post-remediation)

Legend: **VERIFIED COMPLETE** | **PARTIAL** | **NOT IMPLEMENTED** | **BLOCKED**

| # | Area | Status | Code / test evidence | Limits |
|---|------|--------|----------------------|--------|
| 1 | Market-data truth (LIVE/FALLBACK/STALE/EOD) | **PARTIAL** | `market_types.py`, `live_quotes.py`, `freeze_live_sides`, ProvenanceBadge; `test_phase1_market` OK | Live Kotak E2E **BLOCKED** without session |
| 2 | Providers / feeds | **PARTIAL** | Demo refused (`allow_demo_data=False`, demo adapter forbidden); Kotak hub + Yahoo fallback; phase2 tests OK | Credentialed WS e2e **BLOCKED** |
| 3 | Strategies / expectancy gates | **PARTIAL** | `expectancy/gate.py` uses `GATE_PASS_RESEARCH`, strips `EDGE_PROVEN`, `proven=False`; phase5 + strategy_evaluation OK | Survivorship residual; MCX not expectancy-gated (by design) |
| 4 | Swing EOD ingest / calendar | **PARTIAL** | `ingest_scheduler`, `nse_calendar`, holidays JSON; phase4 OK | Operator holiday file; no live NSE sync |
| 5 | MCX desk | **PARTIAL** | Proxy labels, `is_mcx_listed=False`; phase5_mcx OK | Not INR MCX lots/margins |
| 6 | Options / OI | **PARTIAL** | `options_oi`, option_chain routers; inactive→unavailable; test_options_oi OK | Live chain **BLOCKED** without Kotak |
| 7 | Journal / capital / sizing | **PARTIAL** | `trade_ledger`, `position_sizing`; unit tests OK | User-entered ≠ broker fills |
| 8 | Market events / holiday freshness | **PARTIAL** | `market_events.py` `is_current`/`presented_as_current`; UI “STALE — not current”; RealHolidayFileTests + Jest OK | `as_of` still `2026-01-15` until operator verifies circular |
| 9 | Signal availability / ledger honesty | **PARTIAL** | `signal_availability.py`; demo strip; board codes; ExpectancyHonestyBanner on Index/Intraday; tests OK | Ledger still empty until non-demo admin publish (by design) |
| 10 | Ops / API_KEY / auth | **PARTIAL** | Loopback boot refuse; `ApiKeyMiddleware` gates evaluate + GET harness; posture inventory; phase7 + strategy_evaluation OK | AUTH off by default; empty `API_KEY` = open evaluate for local UI |
| 11 | LLM explanation layer (server snapshot) | **NOT IMPLEMENTED** | Design-only (canvas); existing `/api/analyze` still client-supplied signal commentary | Must not originate/alter signals (current analyze is commentary-only — verified by route role, not new snapshot builder) |
| 12 | Order execution / guaranteed returns | **NOT IMPLEMENTED** (correct) | No broker order APIs; disclaimers in disclosure/gates | — |

---

## Critical honesty checks (this session)

| Check | Result | Evidence |
|-------|--------|----------|
| Stale/fallback cannot masquerade as broker LIVE | **Pass (unit)** | `freeze_live_sides` sets `is_current_live=False`, BUY/SELL→HOLD; SignalBoard holds STRONG on insuff/proxy/gate fail; ProvenanceBadge maps FALLBACK≠LIVE |
| Stale data cannot create fresh signals | **Pass (unit)** | annotate + freeze coerce; weekly_swing `require_fresh` → status stale with empty candidates; holiday/events `presented_as_current=false` when stale |
| LLM cannot originate/alter signals | **Pass (architecture)** | Signals from consultant builders + gates only; `/api/analyze` returns labeled AI commentary; no write to `signal_records` from analyze |
| No secrets in frontend / logs / tests | **Pass (spot)** | Frontend has no embedded API keys (only UX copy mentioning `KOTAK_CONSUMER_KEY`); analyze logs `key_source` not key; tests assert key absent from 401/200 bodies; health posture omits secret values |
| Demo seed / demo signals | **Pass** | `seed_platform.py` REFUSED; `/api/platform/demo/signals` → 410; platform list strips `data_mode=demo` |

---

## Data source & freshness by desk

| Desk | Primary inputs | Freshness / honesty | Verified how |
|------|----------------|---------------------|--------------|
| **Swing** | SQLite EOD + indicators; NIFTY regime | EOD FRESH/STALE via `db.freshness`; BEAR→cash / no new BUYs | Code + consultant path; unit tests |
| **Intraday** | Kotak WS LTP or Yahoo 5m FALLBACK; `bars_5m` for expectancy | Session freeze; expectancy honesty banner; gate strip | Code + Jest desk/banner; phase3/5 fixtures |
| **Index** | Same live path for NIFTY/BN; EOD regime | Same freeze + honesty banner | Code + IndexDesk Jest |
| **MCX** | Yahoo global futures proxy | Explicit not MCX INR; expectancy ungated/proxy | phase5_mcx + McxDesk |

**External blockers:** Kotak TOTP/session for LIVE WS/chain; Yahoo may fail in restricted networks (403 observed in sandbox) — failures surface as unavailable/FALLBACK/ERROR, not invented LIVE.

---

## Security posture (verified)

- `AUTH_ENABLED` default false; synthetic admin when auth off (`auth_deps`).
- Boot refuses public bind + auth off unless `ALLOW_PUBLIC_BIND`.
- When `API_KEY` set: ingest/backtest/ledger/journal/kotak login + **POST `/api/strategy-evaluation/evaluate`** + **GET `?run_harness=true`** require `X-API-Key`.
- Empty `API_KEY`: personal UI walk-forward works (CRA does not send the header) — documented in OPS / `.env.example`.
- LLM vault: encrypted server-side; GET never returns plaintext key.

---

## Remediation batches (completed earlier; not re-implemented this pass)

| Batch | ID | Version tag |
|-------|-----|-------------|
| 1 | AUDIT-P0-001 `EDGE_PROVEN`→`GATE_PASS_RESEARCH` | ≤5.12.x |
| 2 | AUDIT-P0-002 version asserts | — |
| 3 | AUDIT-P0-LEDGER-001 signal availability / ledger honesty | 5.12.1 |
| 4 | AUDIT-P1-003 expectancy honesty UI Index/Intraday | 5.12.2 |
| 5 | AUDIT-P1-004 holiday stale not-current | 5.12.3 |
| 6 | AUDIT-P1-005 API_KEY evaluate (+ GET harness) | 5.12.4 |

Open backlog (unchanged this audit): **AUDIT-P0-LEDGER-002** (destructive demo row hygiene — needs explicit OK); **AUDIT-P2-006+** (credentialed live harness); optional LLM **server-snapshot** explain design (not implemented).

---

## Uncommitted changes

Product tree at HEAD `86fd559` was clean. **This audit pass leaves only documentation dirty:**

- `FINAL_REVERSE_ENGINEERING_AUDIT.md` (rewritten post-remediation report)
- `DESK_UPGRADE_TRACKER.md` (batches 3–6 + post-remediation section)

No application code, tests, or config changed during this audit.

---

## Stop

Final audit complete. **No additional product fixes** made during this audit pass. Awaiting review / next approved batch.
