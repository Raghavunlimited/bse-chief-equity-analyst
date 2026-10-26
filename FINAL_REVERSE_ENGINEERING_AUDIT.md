# Final Reverse-Engineering Audit — Swing Desk

**Repository:** `bse-chief-equity-analyst`  
**Git HEAD (last commit):** `92e3bac` on `main` (working tree dirty — Phases 0–7 + follow-ons uncommitted)  
**Code version string:** `5.12.0-strategy-eval` (`backend/app/main.py`)  
**Audit date:** 2026-10-26  
**Method:** Treat tracker/docs/UI as claims; verify against code + tests run this session.  
**Deployment claim:** Personal/local research desk only — `production_ready_claim: false` (verified in `ops_security.security_posture`).

---

## Baseline test/build results (run this session — before remediations)

### Backend (unittest modules)

| Module | Result | Notes |
|--------|--------|-------|
| `test_phase1_market` | **16 OK** | |
| `test_phase2_kotak_feed` | **9 OK** | |
| `test_phase2_provider` | **FAIL 1** | `FeedStatusApiTests.test_feed_status_no_secrets` — `APP_VERSION` pin stops at `5.7` |
| `test_phase3_bars` | **FAIL 1** | `VersionTests.test_app_version_p3` — pin stops at `5.7` |
| `test_phase3_option_chain` | **8 OK** | |
| `test_phase4_eod` | **FAIL 1** | `ApiTests.test_ingest_status_exposes_calendar_and_version` — pin stops at `5.7` |
| `test_phase4_chart` | **3 OK** | |
| `test_phase5_mcx` | **FAIL 1** | `ApiTests.test_consultant_mcx_200` — pin stops at `5.7` |
| `test_phase5_expectancy` | **FAIL 1** | `TestAppVersion.test_version_phase5` — follow-on tags incomplete |
| `test_phase6_chart` | **FAIL 1** | `DepthAndOptionApiTests.test_depth_unavailable_when_no_book` — pin stops at `5.7` |
| `test_phase7_ops` | **12 OK** | |
| `test_options_oi` | **10 OK** | |
| `test_trade_ledger` | **11 OK** | Network 403 noise on Yahoo probe in one privacy path |
| `test_position_sizing` | **20 OK** | |
| `test_market_events` | **12 OK** | |
| `test_strategy_evaluation` | **9 OK** | |
| `test_mvp_platform` | **4 OK** | |
| `test_methodology` | **8 OK** | |
| `test_analyze_validation` | **9 OK** | |
| `test_crypto_adapters` | **4 OK** | |
| **Modules failed** | **6** | All failures observed: brittle `APP_VERSION` assertions |

Commands:

```text
cd backend && python -c '<runner over listed test_* modules>'
# SUMMARY_FAIL_MODULES 6
```

### Frontend

```text
CI=true npm test -- --watchAll=false
→ Test Suites: 10 passed, 10 total; Tests: 25 passed, 25 total

npm run build
→ Compiled successfully (OK)
```

**Implication:** `.github/workflows/ci.yml` runs the failing phase modules → **CI would be red** on this tree until version asserts are fixed.

---

## Feature status matrix

Legend: **VERIFIED COMPLETE** | **PARTIAL** | **NOT IMPLEMENTED** | **BLOCKED**

| # | Area | Status | Evidence (code / tests) | Risks / limits |
|---|------|--------|-------------------------|----------------|
| 1 | Market-data truth | **PARTIAL** | `market_types.py` states LIVE/FALLBACK/STALE/EOD; `live_quotes.py` + `annotate_live_quote`; `test_phase1_market` OK | Yahoo FALLBACK can look “fresh” if UI under-emphasizes; health ≠ data ready (`/api/health` vs `/api/health/ready`) |
| 2 | Providers / feeds | **PARTIAL** | Kotak WS path + Yahoo fallback; demo adapter refused (`adapters/registry.py`, `config.allow_demo_data=False`); `test_phase2_*` | Live Kotak e2e **BLOCKED** without credentials; Yahoo fetch can fail (sandbox/network); SFeed migration not done |
| 3 | Strategies / evaluation | **PARTIAL** | Swing EOD + 5m cores; expectancy harness + `strategy_evaluation.py`; gates in `expectancy/gate.py`; `test_phase5_expectancy`, `test_strategy_evaluation` | **Misleading:** STRONG path tags `EDGE_PROVEN` while `proven=False` (`gate.py` L248–251). Survivorship/multiple-testing residual. MCX not in harness |
| 4 | Swing EOD ingest | **PARTIAL** | `ingest_scheduler.py`, `nse_calendar.py`, `nse_holidays.json`, `test_phase4_eod` (version assert fails) | Holiday file operator-maintained / can be **stale**; not live NSE sync |
| 5 | MCX | **PARTIAL** | `mcx_instruments.py`, `strategy/mcx.py` proxy labels; `test_phase5_mcx` (version assert fails) | Correctly not INR MCX; lot sizing unavailable; expectancy disabled |
| 6 | Options / OI | **PARTIAL** | `options_oi.py`, option_chain routers; inactive → unavailable; OI/PCR “not a signal”; `test_options_oi` OK | Live chain e2e **BLOCKED** without Kotak session; no testable put/call trade rules |
| 7 | Journal / capital / sizing | **PARTIAL** | `trade_ledger.py`, `position_sizing.py`; UI components; unit tests OK | User-entered ≠ broker fills (labeled). F&O sizing needs verified lot/margin. Ledger privacy: health omits rows |
| 8 | Market events | **PARTIAL** | `market_events.py`; empty operator events; NSE holidays; FO optional; `test_market_events` OK | NSE holiday `as_of` may mark feed **stale**; no commercial calendar license (by design) |
| 9 | Ops / security / release | **PARTIAL** | `ops_security.assert_safe_boot`, loopback default, `production_ready_claim=false`; `test_phase7_ops` OK | AUTH off by default. When `API_KEY` set: ledger/ingest/backtest/kotak login/journal + strategy evaluate (+ GET harness). Empty key = personal UI frictionless |

---

## Critical findings (contradictions)

| ID | Finding | Claim vs evidence |
|----|---------|-------------------|
| C1 | `EDGE_PROVEN` tag on STRONG badges | Tracker/strategy-eval say never “proven”; `metrics_pub["proven"]=False`; but tags include `EDGE_PROVEN` and UI can show tags (`SignalBoard.js` tags strip) |
| C2 | Tracker “phases complete” vs CI | Tracker reports green phase modules; baseline this session: **6 phase modules FAIL** on version asserts |
| C3 | `gate.py` module docstring “proven edge” | Conflicts with disclaimer “Gate pass ≠ proven edge” |
| C4 | Uncommitted mega-diff | Last commit is v4-era (`92e3bac`); all phase work is local dirty/untracked — not yet a reviewed release artifact |
| C5 | Holiday calendar freshness | `nse_holidays.json` `as_of: 2026-01-15` vs 2026-10-26 → **stale by design**; P1-004 labels not-current (`5.12.3`). as_of unchanged pending operator circular |
| C6 | Signal ledger empty | UI “No signals” + seed_platform hint vs 10 `data_mode=demo` rows stripped by `platform.list_signals`; consultant desks never write ledger. Full write-up: `SIGNAL_LEDGER_EMPTY_DIAGNOSIS.md` |

---

## Prioritized backlog

| ID | Sev | Title | Deps | Acceptance criteria | Proposed tests |
|----|-----|-------|------|---------------------|----------------|
| **AUDIT-P0-001** | **P0** | Remove misleading `EDGE_PROVEN` tag; align gate language | none | STRONG badges never attach `EDGE_PROVEN`; `proven` remains false; tag uses research wording (e.g. `GATE_PASS_RESEARCH`); UI does not display “proven” from tags | Unit test on `apply_expectancy_gate` with mocked metrics that pass gates |
| **AUDIT-P0-002** | **P0** | Fix brittle `APP_VERSION` asserts in phase tests so CI matches `5.12.x` | none | All CI backend modules green without weakening real assertions | Re-run failed phase modules |
| **AUDIT-P0-LEDGER-001** | **P0** | Honest Signal ledger empty state + availability codes | **DONE** `5.12.1` | Empty copy drops run-seed; surfaces `ledger_availability` / demo filter; board codes distinguish qualifying / no_qualifying / data_blocked / gate_blocked; display meta on signals | `test_signal_availability` + SignalHistory/SignalBoard Jest |
| AUDIT-P0-LEDGER-002 | P0? | Optional delete/re-tag legacy demo `signal_records` | explicit OK | Operator-approved only; never invent live rows | Destructive — skip unless approved |
| **AUDIT-P1-003** | **P1** | Surface expectancy `proxy` / `insufficient_history` / gate fails on Index/Intraday | P0-001 | **DONE** `5.12.2` — desk banner + card strip + STRONG held; no threshold changes | Backend + Jest evidence in batch 4 |
| **AUDIT-P1-004** | **P1** | NSE holiday snapshot freshness / not-current labeling | none | **DONE** `5.12.3` — `as_of` remains `2026-01-15` (no unverified bump); stale feed `is_current=false` / `presented_as_current=false`; UI “STALE — not current” | `test_market_events` RealHolidayFileTests + MarketEventsCalendar Jest |
| **AUDIT-P1-005** | **P1** | API_KEY / auth posture for expensive evaluate POST | none | **DONE** `5.12.4` — least-disruptive: empty `API_KEY` open on loopback; when set, `X-API-Key` on `POST /evaluate` + `GET ?run_harness=true`; meta/audit/summary stay open; AUTH stays off by default | `test_strategy_evaluation` + `test_phase7_ops` |
| AUDIT-P2-006 | P2 blocked | Live Kotak WS + option-chain e2e harness (credentialed) | saved fixture | No saved WebSocket feed fixture and no saved option-chain fixture. No contract test added. No broker payload created. Existing tests: `test_phase2_kotak_feed` 9 OK, `test_phase3_option_chain` 8 OK. | Replay test waits on a recorded fixture |
| **AUDIT-P2-007** | **P2 done** | Point-in-time universe for swing WF (survivorship) | data | Done: swing walk-forward screens the current stored snapshot for each date. No point-in-time list was added. `universe_honesty` on the evaluation report says delisted names are absent; the evaluation UI shows that sentence. `proven` stays false. | `test_strategy_evaluation.UniverseHonestyTests` |
| AUDIT-P2-008 | P2 | Commit/review strategy for dirty tree | human | Explicit release commit after P0s | CI green |

---

## Provider / credential blockers

- **Kotak Neo WS / option chain LIVE:** Not verified end-to-end in CI; requires TOTP/session. Status endpoints exist; idle = unavailable (verified in unit tests with mocks).
- **Yahoo:** Research FALLBACK; network failures observed in tests (403 tunnel) — treated as fetch fail, not invented quotes.
- **NSE holidays:** No live circular API; operator JSON only.
- **MCX INR contracts / lots / margins:** Not available — proxy only (verified).

---

## Schema / config / security notes (no destructive migration framework)

- **Schema:** `CREATE TABLE IF NOT EXISTS` for `expectancy_metrics`, `bars_5m`, trade ledger DB (`data/trade_ledger.db`), holiday/events JSON — **no formal migration runner**.
- **Config:** `.env.example` documents `BIND_HOST`, `AUTH_ENABLED`, `API_KEY`, Kotak keys; `frontend/.env.development` sets CRA host check workaround.
- **Security:** Boot refuses public bind with auth off; demo forbidden; ledger mutations API-key gated when set; secrets not returned in health (phase2 test intent — currently fails only on version pin).

---

## Remediation batch 1 — AUDIT-P0-001 (approved)

Misleading `EDGE_PROVEN` → `GATE_PASS_RESEARCH`. `TestGate` 4 OK.

## Remediation batch 2 — AUDIT-P0-002 (approved / done)

**Selected:** Brittle `APP_VERSION` asserts in six phase modules.  
**Change:** `^5\.(\d+)\.` with minor ≥ phase floor (2/3/4/5/5/6). Current `5.12.0-strategy-eval` passes; `5.1.x` still fails phase-2+.  
**Six modules:** all OK (15+14+14+12+14+12 = 81 tests).  
**CI-equivalent backend suite:** `TOTAL_TESTS=216 FAIL_MODULES=0` (20 modules + methodology assert).  
**Not claimed:** remote GitHub Actions / frontend CI job (not run this batch).

---

## Diagnosis — empty Signal ledger (2026-10-26)

**Doc:** `SIGNAL_LEDGER_EMPTY_DIAGNOSIS.md`  
**Root cause (verified):** Platform API strips `data_mode=demo`; local DB has **10/10 demo** rows → API `count=0` + `filtered_demo_rows` &gt; 0. Ledger ≠ consultant boards (no auto-publish).

---

## Remediation batch 3 — AUDIT-P0-LEDGER-001 (approved / done)

**Version:** `5.12.1-signal-availability`  
**Scope:** Signal-availability honesty only — **no** strategy threshold changes, **no** manufactured ledger rows, **no** LLM, **no** demo re-seed.

### What shipped

- `backend/app/signal_availability.py` — classifies `qualifying` / `no_qualifying` / `data_blocked` / `gate_blocked`; ledger `ledger_empty` / `ledger_demo_filtered` / `ledger_has_published`; annotates desk, strategy, instrument, direction, data_source, data_timestamp, data_status, gate_result; stale/halted never keep BUY/SELL.
- Consultant builders (swing/intraday/index/mcx) attach `signal_availability` + annotated calls; intraday/index pass through feed honesty fields.
- `GET /api/platform/signals` returns `ledger_availability` + enriched rows (demo still stripped).
- UI: `SignalAvailabilityBanner`; `SignalHistory` drops “run seed_platform”; `SignalBoard` + desks show availability + gate/meta; Swing hero distinguishes stale vs strategy miss.

### Tests

| Suite | Result |
|-------|--------|
| `test_signal_availability` | **12 OK** |
| CI-equivalent backend (21 modules) | **TOTAL_TESTS=228 FAIL_MODULES=0** |
| Frontend `CI=true npm test` | **11 suites / 32 tests passed** |

### Not done (needs separate approval)

- **AUDIT-P0-LEDGER-002** delete/re-tag legacy demo `signal_records`
- Auto-wire consultant → platform ledger
- AUDIT-P2-006+

---

## Remediation batch 4 — AUDIT-P1-003 (approved / done)

**Version:** `5.12.2-expectancy-honesty-ui`  
**Scope:** Visibility only on Index / Intraday (and shared SignalBoard strip). **No** strategy threshold changes; **no** stale→fresh signal path changes.

### Verified before change

- Gate still blocks STRONG on proxy / insufficient 5m / failed gates (`expectancy/gate.py`).
- Card already had strip + `strongHold` hold styling; **Index/Intraday desks lacked a board-level banner**.

### What shipped

- `summarize_expectancy_honesty` → board field `expectancy_honesty` via `attach_board_availability`.
- `ExpectancyHonestyBanner` on `IntradayDesk` + `IndexDesk` (counts for thin 5m / proxy / gate fails).
- Stronger card strip copy: `insufficient — STRONG blocked`, `ungated — STRONG blocked`, gate fail reasons.

### Tests (exact)

| Suite | Result |
|-------|--------|
| `test_signal_availability` | **15 OK** (incl. 3 new honesty summary tests) |
| CI-equivalent backend (21 modules) | **TOTAL_TESTS=232 FAIL_MODULES=0** |
| Frontend `CI=true npm test` | **14 suites / 36 tests passed** |
| Targeted: SignalBoard + ExpectancyHonesty + IntradayDesk + IndexDesk | **14 passed** |

### Changed files

- `backend/app/signal_availability.py`, `backend/app/main.py`, `backend/test_signal_availability.py`
- `frontend/src/components/ExpectancyHonestyBanner.js` (+test)
- `frontend/src/components/IntradayDesk.js` (+test), `IndexDesk.js` (+test)
- `frontend/src/components/SignalBoard.js`, `SignalBoard.test.js`, `App.css`

**Stopped for review after batch 4.** Continued with P1-004 below.

---

## Remediation batch 5 — AUDIT-P1-004 (approved / done)

**Version:** `5.12.3-holiday-freshness`  
**Scope:** Holiday snapshot source/freshness honesty only. **`as_of` not changed** (still `2026-01-15`). No live NSE download.

### Review evidence

| Item | Finding |
|------|---------|
| Source | Operator-maintained `backend/app/data/nse_holidays.json` (`operator_maintained_snapshot`) — NSE cash holiday circular facts; not an API |
| `as_of` | **2026-01-15** (unchanged — no operator-verified circular provided this session) |
| Freshness window | `stale_after_days: 120` (now explicit in JSON; was default) |
| Frozen clock `2026-10-26` | Feed **stale**; age &gt; 120d; events still listed but `presented_as_current=false` |

### What shipped

- Feed/event flags: `is_current`, `presented_as_current` (false when stale/unavailable).
- Stale reasons explicitly say **not a current calendar**.
- UI: banner + feed chip + event chip **“STALE — not current”**; `data-presented-as-current="false"`.
- OPS note documents committed `as_of` and no-bump policy.

### Tests (exact)

| Suite | Result |
|-------|--------|
| `test_market_events` | **13 OK** (incl. `RealHolidayFileTests` vs committed file) |
| Frontend MarketEventsCalendar | **2 OK** |
| Full frontend `CI=true npm test` | **14 suites / 36 tests passed** |

### Changed files

- `backend/app/market_events.py`, `backend/app/data/nse_holidays.json` (added `stale_after_days` only), `backend/test_market_events.py`, `backend/app/main.py`
- `frontend/src/components/MarketEventsCalendar.js`, `.test.js`
- `docs/OPS.md`, `FINAL_REVERSE_ENGINEERING_AUDIT.md`

**Stopped for review after batch 5.** Continued with P1-005 below.

---

## Remediation batch 6 — AUDIT-P1-005 (approved / done)

**Version:** `5.12.4-api-key-evaluate`  
**Scope:** Auth / API_KEY posture for expensive strategy evaluation — verify + document + close GET harness gap. No AUTH_ENABLED flip.

### Inspection (before change)

| Route | Method | Cost | Gate when `API_KEY` set |
|-------|--------|------|-------------------------|
| `/api/strategy-evaluation/evaluate` | POST | Walk-forward / OOS | Already in `_PROTECTED_POST_PATHS` |
| `/api/strategy-evaluation?run_harness=true` | GET | Same harness | **Was open** — closed this batch |
| `/meta`, `/audit`, `?run_harness=false` | GET | Cheap / stored | Open (unchanged) |
| ingest / backtest / ledger / journal / kotak login | mutate | High | Existing prefixes |
| `/api/analyze`, position-sizing | POST | Separate | Not in this gate (vault/BYOK / research calc) |

Frontend `runStrategyEvaluation` → POST evaluate; **does not send** `X-API-Key`.

### Least-disruptive safe posture (adopted)

1. Default personal loopback: `API_KEY=` empty → gate **off** (UI “Run walk-forward” works).
2. When `API_KEY` is set (hardened local / non-loopback): require `X-API-Key` for POST evaluate **and** GET `run_harness=true`.
3. Do **not** turn on `AUTH_ENABLED` just for this route.
4. Document that with a key set, UI evaluate needs curl/`X-API-Key` (or leave key empty).

### Tests (exact)

| Suite | Result |
|-------|--------|
| `test_strategy_evaluation` | **11 OK** (evaluate: missing/wrong key → 401; valid key → 200; GET harness gated; meta/audit/summary open; no key leak) |
| `test_phase7_ops` | **12 OK** (posture lists inventory; secret value never in health) |

### Docs / config

- `docs/OPS.md`, `docs/CTO_READINESS.md`, `backend/.env.example` — evaluate + GET harness + local-dev UI note
- Health/meta expose secret-free `api_key_gate` inventory

### Changed files

- `backend/app/security.py`, `ops_security.py`, `routers/strategy_evaluation.py`, `main.py`
- `backend/test_strategy_evaluation.py`, `test_phase7_ops.py`
- `docs/OPS.md`, `docs/CTO_READINESS.md`, `backend/.env.example`, tracker

**Stopped for review.** Not started: P2+.
