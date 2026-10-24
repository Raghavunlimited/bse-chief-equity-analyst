# Manual QA script — Swing Desk UI

Run against local stack (API `:8000`, UI via `start.sh` / CRA proxy). Mark each step Pass / Fail. Pair with [ACCEPTANCE.md](./ACCEPTANCE.md) and `backend/test_production_suite.py`.

**Environment:** _______________ **Build:** _______________ **Tester:** _______________ **Date:** _______________

---

## A. Boot & chrome (~3 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| A1 | Open UI root | Brand “Swing Desk”, no blank page / console red errors on load | |
| A2 | Confirm desk tabs **Swing / Intraday / MCX** | Active tab highlighted; blurb visible | |
| A3 | Header: Test Kotak / Refresh / Force full present | Buttons enabled when idle | |
| A4 | Search “REL” | Hits include RELIANCE; click opens stock modal | |

---

## B. Swing desk + capital planner (~8 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| B1 | Land on Swing | Hero “This week’s setups”, week label (e.g. `2026-W43`), regime chip | |
| B2 | Regime / provenance / stale chips | Click chip → explanation panel; demo vs Kotak honest | |
| B3 | CapitalDesk: set capital ₹5L, risk 1%, target 3%, Apply | Desk reloads; risk ₹ and target ₹ update | |
| B4 | Raise target % to unreachable (e.g. 15%) | Planner shows not reachable / caution — no fake promise | |
| B5 | Weekly picks or consultant SignalBoard | Cards/calls with thesis; cash week shows HOLD/cash copy | |
| B6 | Open a pick → stock modal | Financials section clear; chart if EOD exists | |
| B7 | If SignalBoard present: note BUY/SELL/HOLD + confidence bar | Sides match consultant vocabulary | |

---

## C. Week journal (~5 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| C1 | Scroll to WeekJournal (Swing desk) | Current ISO week shown | |
| C2 | Log a watch: symbol `TESTSYM`, invested off, notes “QA” | Success toast/message; research-only disclaimer | |
| C3 | Reload / re-fetch journal | Entry visible for the week | |
| C4 | Log invested trade with capital + PnL | Running week P&L updates; copy says research log not broker fill | |
| C5 | From pick card “Log” (if present) | Focuses journal with symbol prefilled | |

---

## D. Intraday desk (~5 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| D1 | Switch to **Intraday** | Hero copy for 5m NSE bias; SignalBoard or legacy tape | |
| D2 | Wait one poll cycle (~15s) | Rows refresh or poll indicator; no crash | |
| D3 | Off-hours | Explicit off-session / residue note; confidence discounted if consultant | |
| D4 | Open Analyze on one call (if button present) | See section F | |

---

## E. MCX desk (~4 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| E1 | Switch to **MCX** | Gold / Silver / Crude / NatGas / Copper (or equiv.) | |
| E2 | Leverage / lot mapping warning | Visible on board or call tags | |
| E3 | USDINR context (if shown) | Labeled as FX context, not a tip | |

---

## F. LLM analyze modal (~7 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| F1 | Open Settings (drawer/modal) | Provider openai/anthropic; key field; save/clear | |
| F2 | Clear any saved key | localStorage key removed | |
| F3 | Click **Analyze with LLM** on a signal | Prompt to add key — **no** server 500 | |
| F4 | Save a dummy short key (<8 chars) | Client or API rejects; clear validation | |
| F5 | Save a long fake key; Analyze | 401/502 honest error **or** analysis JSON; disclaimer shown | |
| F6 | DevTools Network: `POST /api/analyze` | Missing key → **422**; with key → body has `api_key` (BYOK) only for this call | |
| F7 | Clear key after test | Key gone from localStorage | |

---

## G. Feeds & ingest (optional, ~10 min)

| # | Step | Expect | P/F |
|---|------|--------|-----|
| G1 | Test Kotak | OK + candle count, or honest failure | |
| G2 | Refresh data (non-force) | Progress bar; desk reloads when done | |
| G3 | Force full (skip if long ingest) | Concurrent Kotak workers in progress text; UI stays usable | |

---

## H. Regression / negative

| # | Step | Expect | P/F |
|---|------|--------|-----|
| H1 | No Groww chips or `/api/feeds/groww` | Absent | |
| H2 | Stop API; reload UI | Clear error, not infinite spinner forever | |
| H3 | Mobile width ~390px | Tabs usable; no horizontal trap on hero | |

---

## Sign-off

**Overall:** PASS / FAIL **Blockers:** _______________
