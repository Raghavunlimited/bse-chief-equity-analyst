# Diagnosis: why “analyzed signals” look empty (2026-10-26)

**Scope:** Investigation only — no product fixes applied.  
**Git:** `3e94f82` on `main`, working tree clean at investigation start (this file may be uncommitted).  
**Method:** Code path trace + TestClient against local `backend/data/swing_trader.db` (no live Kotak session). Yahoo fetches failed with tunnel 403 in this harness (treated as unavailable, not invented LIVE).

---

## Verdict (short)

You are not looking at a broken strategy pipeline. Three different surfaces are easy to confuse:

| Surface | What it is | Current local result |
|---------|------------|----------------------|
| **Consultant boards** (Swing / Intraday / Index / MCX) | Live research cards from deterministic strategies | **Cards exist** — almost all **HOLD**; **0 BUY/SELL** |
| **Signal ledger** (`SignalHistory`) | Admin-published append-only notes | **Empty** — 10 DB rows all `data_mode=demo`, filtered out; desks never auto-publish |
| **Analyze with LLM** | Optional commentary on a card you already have | Needs a non-empty card **plus** an API key (vault or one-shot). Does **not** create signals |

There is **one clear honesty defect:** Swing cash/BEAR weeks are labeled **`gate_blocked`** (“insufficient history or expectancy/risk gates failed”) even when EOD is **FRESH** and the real reason is regime/strategy cash. Unit tests already expect cash → `no_qualifying`; production boards attach expectancy `passed=False` on HOLDs and flip the code.

---

## Reproduction (this session)

```text
GET /api/platform/signals?category=swing&history=true
→ count=0, filtered_demo_rows=4, ledger_availability=ledger_demo_filtered

GET /api/consultant/swing
→ status=cash, data_status=FRESH, buy=0 hold=4, avail=gate_blocked
→ message/detail: "NIFTY below SMA50 — no new swings"
→ regime BEAR, allow_trading=false
→ HOLD calls still have expectancy.gates.passed=false (N<30 …)

GET /api/consultant/intraday|index
→ avail=data_blocked, signal_generation=halted, message POST-MARKET freeze
→ Yahoo FALLBACK 403 → UNAVAILABLE / not LIVE

GET /api/consultant/mcx
→ HOLD×6, avail=data_blocked (quotes unavailable / proxy tape; not MCX INR LIVE)
```

Local EOD: `MAX(trade_date)=2026-10-26`, ~2709 symbols — Swing data is present.  
`bars_5m`: 2059 rows same session date — history exists but post-market freeze still halts live sides.

---

## Per-desk classification

| Desk | Generated? | Actionable BUY/SELL? | Why | Availability code (observed) | Correct class? |
|------|------------|----------------------|-----|------------------------------|----------------|
| Swing | Yes (HOLD + radar) | No | BEAR / NIFTY &lt; SMA50 → cash by design | `gate_blocked` | **Wrong** → should be `no_qualifying` |
| Intraday | Yes (HOLD) | No | After close + feed halt; Yahoo fail ≠ LIVE | `data_blocked` | Correct |
| Index | Yes (HOLD×2) | No | Same post-market halt | `data_blocked` | Correct |
| MCX | Yes (HOLD×6) | No | Yahoo proxy unavailable; never broker LIVE | `data_blocked` | Acceptable (data missing); proxy gate is separate |
| Ledger | N/A | N/A | Demo strip + no admin publish path in personal AUTH-off UI | `ledger_demo_filtered` | By design |

**Data sources (do not call Yahoo “live broker”):**

- Swing: SQLite EOD / indicators (`price_kind` EOD) — **FRESH** today.  
- Intraday/Index: Kotak WS → `LIVE` only when connected; else Yahoo 5m → **`FALLBACK`**; age/session → **`STALE`** + freeze.  
- MCX: Yahoo global futures proxy — **not** exchange MCX INR.

**LLM:** `/api/analyze` comments on client-supplied signal JSON only. No write to `signal_records`. No origin/alter of desk sides.

**Admin publish UI:** Shown only if `authUser.role==='admin' && email !== 'operator@local'`. AuthGate personal bypass uses `operator@local` → **Admin button hidden** → beginners cannot fill the ledger from the UI even though API admin exists as `dev@local` when AUTH off.

---

## Root causes (ordered)

1. **Expectation mismatch** — “Signals” on desks ≠ “Signal ledger”. Ledger empty is expected without non-demo admin publish.  
2. **No qualifying BUY/SELL** — Swing cash week (real). Intraday/Index halted after market close (real).  
3. **Honesty bug** — `_gate_failure_dominant` treats expectancy `passed=False` on cash HOLDs as `gate_blocked`, overriding strategy cash messaging (`test_no_qualifying_cash_regime` does not attach expectancy fails; live `gate_calls` does).  
4. **Optional:** personal UI hides Admin → ledger stays empty forever for typical AUTH-off users (docs/product, not strategy).

---

## Proposed minimal fix (needs approval — not applied)

### Batch A — availability honesty (recommended)

**File:** `backend/app/signal_availability.py`  
**Change:** Before classifying `gate_blocked`, if board `status == "cash"` (or tags/CASH_WEEK / BEAR_GATE with FRESH/`data_blocked` false) and `actionable == 0` → **`no_qualifying`**. Do **not** change strategy thresholds, expectancy math, or auto-publish.

**Tests:** Extend `test_signal_availability.py`:

- Cash + FRESH + HOLD + `expectancy.gates.passed=False` / `N<30` → still `NO_QUALIFYING` (regression for today’s Swing payload shape).  
- Keep existing insufficient_history → `GATE_BLOCKED`.  
- Keep feed halt → `DATA_BLOCKED`.

**Frontend:** None required if banner already uses `availability.label/detail` (detail already shows BEAR message; label would stop lying).

### Batch B — ledger UX (optional, separate approval)

Pick **one**:

- **B1 (docs-only):** Manual explains ledger is optional admin notes; desk boards are the research signals.  
- **B2 (tiny UI):** Allow Admin for AUTH-off local operator (`operator@local` / `dev@local`) with clear “publish research note” copy — still no auto-publish from desks.  
- **B3 (destructive):** Delete demo `signal_records` (needs explicit OK; prior AUDIT-P0-LEDGER-002).

**Do not:** auto-write consultant calls into the ledger; loosen gates; invent BUY signals; add LLM that creates sides.

### Batch C — beginner manual (after UI verify)

**Primary:** `docs/PERSONAL_USE.md` (linked from `QUICKSTART.md`).  
**Also light touch:** `QUICKSTART.md` troubleshooting (“empty ledger” / “only HOLD” / “Analyze 422”).  
**PDFs** `Swing_Desk_Personal_Guide.pdf` / `Swing_Desk_User_Guide.pdf` are stubby v4.1 — regenerate from markdown **or** mark markdown as source of truth (no invented screenshots).

Manual must cover: start via `./start.sh`, four desks, LIVE/FALLBACK/EOD/STALE, cash vs blocked vs no qualifying, LLM explain-only + key setup without pasting secrets, research-only / no orders / no return guarantee.

---

## Test plan (after approval)

```text
cd backend
export AUTH_ENABLED=false SECRET_KEY='ci-test-secret-key-32chars-min!!' MARKET_DATA_ADAPTER=live EOD_INGEST_SCHEDULE_ENABLED=false
python -m unittest test_signal_availability -v
# plus any touched UI:
cd ../frontend && CI=true npm test -- --watchAll=false --testPathPattern='SignalAvailability|SignalHistory|SignalBoard'
npm run build
```

Deterministic fixtures + controllable clocks only; no live credentials.

---

## Stop

Awaiting approval of **Batch A** and/or **B** and **C**. No behavior or manual edits applied in this pass beyond this diagnosis file.
