# Diagnosis: empty Signal ledger (no implementation)

**Date:** 2026-10-26  
**Scope:** Diagnosis only — no strategy/threshold/provider/UI behavior changes applied.  
**Code version:** `5.12.0-strategy-eval`  
**Local DB:** `backend/data/swing_trader.db`

---

## Verdict (short)

The **Signal ledger** (`SignalHistory` → `GET /api/platform/signals`) is **empty because every local `signal_records` row has `data_mode=demo`**, and the platform API **strips all demo rows** before responding. This is **not** caused by expectancy gates, missing EOD, or frontend list bugs.

Separately: the ledger is an **admin-published append-only store**. Consultant desk calls (**Swing / Intraday / Index / MCX**) **never write** into `signal_records`. Even with live research cards on desks, the ledger stays empty until an admin publishes with a **non-demo** `data_mode`.

---

## What “Signal ledger” is

| Layer | Path | Role |
|-------|------|------|
| UI | `frontend/src/components/SignalHistory.js` | “Signal ledger” — loads `/api/platform/signals` |
| API | `backend/app/routers/platform.py` `list_signals` | Lists `signal_records`; **filters `data_mode == demo`** |
| Persist | `PlatformDB.publish_signal` | Only writer (plus revise) — used by **admin** `POST /api/admin/signals` |
| Seed | `backend/seed_platform.py` | **REFUSED** (Phase 1) — cannot repopulate |

Consultant research boards use **different** endpoints (`/api/consultant/{swing,intraday,index,mcx}`) and do **not** persist to the ledger.

---

## End-to-end traces (verified this session)

### A) Signal ledger path (why UI shows “No signals yet”)

```
UI SignalHistory
  → deskAPI.platformSignals({ category, history })
  → GET /api/platform/signals
  → PlatformDB.list_signals(...)   # returns DB rows including demo
  → live_rows = [r for r in rows if data_mode != "demo"]   # ← empties list
  → JSON { signals: [], count: 0, filtered_demo_rows: N }
  → UI: rows.length === 0 → "No signals yet… seed_platform"
```

**Category mapping** (`App.js` `categoryForDesk`):

| Desk | Ledger `category` query |
|------|-------------------------|
| Swing | `swing` |
| Intraday | `intraday` |
| Index | `intraday` (shared — no separate `index` ledger category) |
| MCX | `commodity` |

**Local DB evidence:**

- `signal_records` count = **10** (all `data_mode=demo`, dates ~2026-10-21…24).
- After filter: API `count=0`, `filtered_demo_rows` = 4 / 3 / 3 for swing / intraday / commodity.

**Repro (local API):**

```text
GET /api/platform/signals?category=swing&history=true
→ 200 { count: 0, filtered_demo_rows: 4, signals: [] }
```

**Deterministic fixture (no live markets):** insert demo+live rows → list returns only live; `filtered_demo_rows=1`. Script result: `FIXTURE_OK demo_filtered_live_visible`.

### B) Consultant desks (research cards — not the ledger)

| Desk | Data required | Local availability | Observed this run |
|------|---------------|--------------------|-------------------|
| **Swing** | EOD + indicators in SQLite; NIFTY regime | EOD **FRESH** (`latest_date=2026-10-23`, expected same); ~2709 symbols | `status=cash`, `buy_count=0`, `calls=4` (HOLD/index-style). Reason: **BEAR** — “NIFTY below SMA50 — no new swings”. Gates do not invent BUYs. |
| **Intraday** | LiveQuote / Yahoo 5m or Kotak WS; optional `bars_5m` | `bars_5m` has 2059 rows; Yahoo fetch **failed** in this harness (403 tunnel) | 200 OK, `count=20`, `buy_count=0`, POST-MARKET freeze message |
| **Index** | Same live path for `^NSEI`/`^NSEBANK` + EOD regime | Yahoo failed similarly | 200 OK, `count=2`, `buy_count=0`, POST-MARKET |
| **MCX** | Yahoo global futures + USDINR | Yahoo failed | 200 OK, `count=6`, `buy_count=0` (proxy desk still returned structure; not ledger) |

Expectancy gates affect **STRONG** badges on consultant calls; they do **not** populate or clear the platform ledger.

---

## Exact conditions that prevent ledger rows from appearing

1. **`platform.py` demo strip** (primary, verified):

```74:75:backend/app/routers/platform.py
    # Strip any legacy demo rows from personal desk views
    live_rows = [r for r in rows if str(r.get("data_mode") or "").lower() != "demo"]
```

2. **No auto-publish** from consultant/strategy builders into `signal_records` (by design).

3. **Admin publish** is the only supported fill path (`admin_platform.admin_publish_signal` → `publish_signal`). Default admin form `data_mode: 'delayed'` (non-demo) — new publishes **would** show; existing legacy rows are all demo.

4. **`seed_platform.py` refused** — UI copy still tells users to run it → contradictory / dead end.

5. **Index desk** shares ledger category `intraday` — even with live publishes, Index and Intraday ledgers are the same bucket (product quirk, not root cause of “all empty”).

---

## Does the UI distinguish empty states?

| Condition | Ledger UI today |
|-----------|-----------------|
| No qualifying **consultant** setups | Shown on SignalBoard / desk status (e.g. BEAR cash) — **separate** from ledger |
| Data unavailable / Yahoo fail | Desk banners / consultant messages — **not** reflected in ledger empty copy |
| Stale EOD | Freshness banners on Swing — **not** ledger |
| Insufficient 5m history | Expectancy strip on calls — **not** ledger |
| Empty ledger after demo filter | Single message: *“No signals yet… Ask an admin to publish, or run seed_platform.”* — **does not** mention demo filtering or `filtered_demo_rows` |

**Gap:** UI conflates “no published non-demo ledger rows” with a seed instruction that **cannot** succeed.

---

## Data inputs required vs local setup

| Input | Needed for | Local |
|-------|------------|-------|
| EOD `eod`/`indicators` | Swing consultant | Present, FRESH |
| `bars_5m` | Intraday/Index expectancy | 2059 rows present |
| Kotak WS / Yahoo LTP | Intraday/Index/MCX live bias | Yahoo blocked in this diagnosis run; Kotak session not asserted LIVE |
| Admin (or auth-off synthetic admin) | Ledger publish | `AUTH_ENABLED=false` → synthetic admin; publish API usable |
| Non-demo `signal_records` | Ledger **display** | **None** — all 10 are demo |

---

## Reproduction steps

1. Open Swing desk → scroll to **Signal ledger**.
2. Observe empty state + seed_platform hint.
3. Confirm API:

```bash
curl -s 'http://127.0.0.1:8000/api/platform/signals?category=swing&history=true' | jq '.count,.filtered_demo_rows'
# expect 0 and 4 on this machine’s DB
```

4. Optional SQL: `SELECT data_mode, COUNT(*) FROM signal_records GROUP BY 1` → all `demo`.

---

## Tests run (diagnosis)

| Command / check | Result |
|-----------------|--------|
| SQLite inspect `signal_records` / EOD / bars_5m | 10 demo rows; EOD FRESH; bars_5m 2059 |
| `GET /api/platform/signals` per category | count 0; filtered_demo_rows &gt; 0 |
| Temp DB fixture demo+live → platform list | **FIXTURE_OK** — only live returned |
| `GET /api/consultant/swing` | cash / BEAR / buy 0 (strategy condition, not ledger) |
| Consultant intraday/index/mcx | 200; buy 0; Yahoo errors in sandbox |

No production code changed for this diagnosis.

---

## Fix status

**P0-LEDGER-001 implemented** in `5.12.1-signal-availability` (see `FINAL_REVERSE_ENGINEERING_AUDIT.md` batch 3). Ledger remains empty until non-demo admin publish — by design; UI now explains demo filter and availability codes.

**P0-LEDGER-002 (optional data hygiene):** still needs explicit OK — destructive delete/re-tag of legacy demo rows.

**Out of scope / do not do without separate product approval:**  
Auto-push consultant BUY/SELL into `signal_records`; loosen BEAR cash / expectancy gates; re-enable `seed_platform` demo seed.

---

## Not the root cause (for this empty ledger)

- Expectancy STRONG gates  
- Missing Swing EOD (FRESH)  
- Frontend category typo for Swing (mapping correct; Index shares intraday by design)  
- API 401 on list (auth off → synthetic user)
