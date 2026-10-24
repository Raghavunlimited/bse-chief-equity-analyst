# Swing Desk — Product Requirements Document (PRD)

| Field | Value |
|-------|--------|
| **Product** | Swing Desk (Multi-Market Research Terminal) |
| **Version** | Production Signals MVP → v1.1 |
| **Owner** | Program / Product Management |
| **Stakeholders** | CEO, Engineering, Compliance |
| **Status** | Draft for ship |
| **Codebase** | `bse-chief-equity-analyst` v3.2.x |
| **Last updated** | 2026-10-24 |

---

## 1. Vision

Users open one terminal, choose a desk — **Swing**, **Intraday**, or **Commodity (MCX)** — and receive **professional BUY / SELL / HOLD (FLAT)** research calls with entry, stop, target, confidence context (charts, open interest where available, financials), and an optional **BYO LLM API key** for deeper narrative analysis.

Swing Desk is a **research and process product**, not a broker, PMS, or tipster service. Every surface must reinforce that signals are educational process aids, not guaranteed returns.

---

## 2. Problem

Retail traders juggle Telegram tips, broker terminals, Screener tabs, and ad-hoc charts. They lack:

1. A **desk-scoped** signal board (swing vs scalp vs commodity) with clear BUY/SELL language.
2. **Freshness & provenance** so they know whether data is live, stale, or demo.
3. **Confidence scaffolding** — chart + OI/flow context + financials — before acting.
4. Optional **deeper thesis** without forcing a vendor LLM or storing keys on our servers by default.

---

## 3. Personas

### P1 — Retail swing trader (“Priya”)

- Holds NSE cash equities for **2–10 sessions**; checks the desk weekly and after major market moves.
- Wants: top setups only, regime gate (cash when NIFTY is weak), stop/target, capital sizing, week journal.
- Pain: too many names; no relative-strength filter; no honest “stay in cash” week.
- Success: opens Swing tab Monday, sees 0–2 scored picks or a clear cash/radar state, journals outcomes Friday.

### P2 — Intraday scalper (“Arjun”)

- Trades liquid NSE cash during **09:15–15:30 IST**; needs bias in seconds, not overnight research.
- Wants: LONG/SHORT/FLAT mapped to **BUY / SELL / HOLD**, auto-refresh (~15s), session context, invalidation levels.
- Pain: stale watchlists; no session-state honesty outside market hours.
- Success: during session, desk shows actionable bias with timestamp; outside hours, clearly labeled residue.

### P3 — Commodity / MCX trader (“Meera”)

- Trades Gold, Silver, Crude, NatGas, Copper (and watches USDINR); maps global futures bias to **front-month MCX** lots herself.
- Wants: directional BUY/SELL with MCX contract hint, session move, risk of gaps/leverage called out.
- Pain: INR MCX vs USD futures confusion; no single tape for majors.
- Success: opens MCX desk, sees majors + FX context, maps to her broker’s MCX contract without us placing orders.

---

## 4. Core user journeys

### J1 — Choose a desk and act on a call

1. User lands on Swing Desk UI (`localhost:3000` or production host).
2. Selects **Swing / Intraday / MCX** tab (persisted in local storage).
3. Sees desk-specific hero + signal board with **BUY | SELL | HOLD** (or cash/radar for swing regime).
4. Opens a symbol → chart + financials (+ OI when available) → optional “Deeper analysis” if LLM key set.
5. Sizes risk (Swing capital planner) or notes levels (Intraday/MCX) → **executes elsewhere**.
6. (Swing) Logs trade/watch in **Week Journal**.

### J2 — Trust the feed before trading

1. User checks freshness / provenance chips (KOTAK / Yahoo / DEMO) and stale banners.
2. If stale: **Refresh** or **Force full** ingest; progress shows concurrent workers.
3. **Test Kotak** confirms consumer key health before trusting EOD swing universe.
4. User only acts when status is FRESH (or accepts near-live Yahoo lag for Intraday/MCX).

### J3 — Optional LLM deeper analysis

1. User pastes **own** LLM API key in settings (local/browser or user-scoped secret; never logged).
2. On a signal card, clicks **Analyze** → thesis, risks, what would invalidate the call.
3. Without a key, product still works fully; CTA explains BYO key is optional.

### J4 — Cash / flat week honesty

1. NIFTY regime fails SMA gates → Swing shows **no new entries** + momentum radar, not fake picks.
2. Intraday/MCX may still show session bias with separate disclaimers.
3. Copy never implies “the system is broken” when cash is the correct research outcome.

---

## 5. Product principles

1. **Desk clarity** — one job per tab; no mixed swing/intraday noise.
2. **Honest data** — DEMO / STALE / FRESH always visible; never silent synthetic as live.
3. **Research language** — BUY/SELL are process labels; always paired with disclaimer.
4. **Confidence over volume** — prefer top-N quality over a wall of tickers.
5. **No execution** — size and journal yes; broker orders no (MVP and v1.1).

---

## 6. Acceptance criteria by desk

### 6.1 Swing desk

| ID | Criterion | Pass condition |
|----|-----------|----------------|
| SW-1 | Weekly BUY / HOLD-cash calls | Regime OK → scored setups with entry/stop/target; else cash + radar explained via NIFTY vs SMA20/50 |
| SW-2 | Universe & liquidity | Liquid NSE EQ only (price/turnover gates); ETFs/illiquids excluded from scan |
| SW-3 | Provenance | Chip shows KOTAK (or honest Yahoo/demo); stale banner when EOD old |
| SW-4 | Confidence | Symbol detail: OHLCV chart, RSI/indicators where EOD exists; Screener/Yahoo financials or honest error |
| SW-5 | Capital planner | Capital + target % → position risk sizing; no guarantee language |
| SW-6 | Journal | Save/load week journal entries; research-log disclaimer on save |
| SW-7 | Backtest parity | Live picks and backtest share the same strategy function |
| SW-8 | Signal freshness metric | `latest_eod_age_hours` (or equivalent) exposed in stats/UI; FRESH vs STALE labeled |

### 6.2 Intraday desk

| ID | Criterion | Pass condition |
|----|-----------|----------------|
| ID-1 | BUY / SELL / HOLD board | Map LONG→BUY, SHORT→SELL, FLAT→HOLD for liquid NSE cash watchlist |
| ID-2 | Session honesty | In-session vs pre-market vs after-hours labeled; after-hours = last-session residue |
| ID-3 | Auto-refresh | ~15s poll while tab active; timestamp on last successful fetch |
| ID-4 | Levels | Bias includes invalidation / stop-style levels when price data allows |
| ID-5 | Failure mode | Empty/failed Yahoo → clear empty state, not fake prices |
| ID-6 | Disclaimer | Persistent educational disclaimer on desk |

### 6.3 Commodity (MCX) desk

| ID | Criterion | Pass condition |
|----|-----------|----------------|
| MC-1 | Majors covered | Gold, Silver, Crude, NatGas, Copper + USDINR context |
| MC-2 | BUY / SELL / HOLD | Directional bias from global futures proxy; MCX contract hint shown |
| MC-3 | Mapping copy | Explicit: user maps lot/margin/front-month; we do not place MCX orders |
| MC-4 | Leverage risk | Gap/leverage warning in desk disclaimer |
| MC-5 | Freshness | Last quote time visible; refresh behavior documented |
| MC-6 | OI (MVP-light / v1.1 full) | MVP: show OI when feed provides it, else “OI unavailable”; v1.1: structured OI change vs prior |

### 6.4 Cross-desk (all)

| ID | Criterion | Pass condition |
|----|-----------|----------------|
| X-1 | Desk switcher | Tabs persist selection; hero copy matches desk |
| X-2 | Health | `/api/health` reports version + desks `swing`, `intraday`, `mcx` + Kotak feed status |
| X-3 | Optional LLM | Works without key; with key, analysis endpoint/UI returns structured thesis + risks; key not written to app logs |
| X-4 | Compliance chrome | Global + per-desk research disclaimer; no “guaranteed returns” / “sure shot” copy anywhere in product UI |
| X-5 | No broker execution | No place-order APIs, no TOTP/MPIN order flows in MVP/v1.1 |

---

## 7. Non-goals

Explicitly **out of scope** for MVP and v1.1:

- Broker order placement, OMS, or portfolio sync (Kotak historical OK; trading auth not productized).
- Guaranteed returns, win-rate promises, or “tips” marketing copy.
- Full BSE/NSE board scanning for swing (liquid NSE cash universe only).
- Advisory / discretionary PMS / SEBI RA license packaging (product is research tooling).
- Social feed, copy-trading, or tipster leaderboards.
- Mobile-native apps (responsive web only).
- Multi-user cloud accounts / billing (local/self-host first; accounts = post-v1.1).
- Storing user LLM keys on our servers by default.

---

## 8. MVP vs v1.1

### MVP (must ship — see also ROADMAP.md)

- Three desks with clear BUY/SELL/HOLD (or swing cash) research calls.
- Swing: Kotak/NSE EOD ingest, regime gate, weekly picks, capital planner, journal, chart + financials.
- Intraday: near-live bias board + auto-refresh + session labels.
- MCX: majors + USDINR + contract hints + disclaimers.
- Freshness / provenance / DEMO honesty.
- Optional BYO LLM key → deeper analysis on a signal (graceful without key).
- OI: display when available; honest empty state otherwise.
- Compliance copy on every desk + user guide PDF regenerable.
- Health, stats, QA checklist green for ship.

### v1.1 (next slice after MVP)

- Structured **OI change** panels (FII/DII or futures OI where licensed/available).
- Richer LLM outputs: invalidation checklist, alternate scenarios, desk-aware prompts.
- Signal history / audit log (what was shown at T) for journal correlation.
- Intraday watchlist customization (user-editable symbols).
- MCX: INR-normalized display helpers (still no execution).
- Alert hooks (browser notification or webhook) for regime flip / new swing pick.
- Hardened production deploy profile (env, rate limits, observability dashboards).

---

## 9. Success metrics

| Metric | Definition | MVP target |
|--------|------------|------------|
| **Signal freshness** | Swing: EOD as-of within 1 trading day of last NSE session when Kotak OK. Intraday/MCX: median quote age &lt; 60s during session under normal Yahoo conditions | ≥ 95% of market sessions meet freshness SLOs when upstream is up |
| **Journal completion** | Share of Swing weeks with ≥1 journal save among users who opened ≥1 pick | ≥ 40% of active swing weeks (local telemetry or self-report in dogfood) |
| **Uptime** | API `/api/health` success rate | ≥ 99% over rolling 7 days on the ship host |
| **Desk engagement** | Weekly unique desk switches (Swing ↔ Intraday ↔ MCX) | Dogfood: all 3 desks used in QA week |
| **Trust incidents** | DEMO shown as live, or missing stale banner | **0** P0 incidents |
| **LLM opt-in utility** | Of users who set a key, ≥1 successful Analyze per session | Qualitative dogfood pass |

Instrumentation for MVP may be lightweight (stats endpoint + manual QA). Formal product analytics can land in v1.1.

---

## 10. Risks & compliance copy requirements

### 10.1 Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users treat BUY/SELL as advice | Regulatory / reputation | Mandatory disclaimers; no guarantee language; research framing in PDF + UI |
| Stale or demo data traded as live | User loss / trust break | Provenance chips, stale banners, DEMO badge |
| Yahoo / Kotak outages | Empty desks | Honest empty states; document fallbacks; don’t invent candles |
| LLM hallucination | Misleading thesis | Label as generative assist; show model disclaimer; never override numeric stops from strategy |
| Key leakage | Security | Client-side or env-only key; never log; never commit `.env` |
| Commodity gap / leverage | User blow-ups | MCX-specific leverage/gap copy; lot mapping disclaimer |
| Implied RA / broker status | Compliance | Non-goals + “not investment advice” on every desk |

### 10.2 Required compliance / legal copy (must appear)

**Global footer or persistent chrome (all desks):**

> Research and education only. Not investment advice. Not a SEBI-registered Research Analyst product presentation. Markets can gap; stops can slip. Past backtests and signals do not guarantee future returns. You alone decide whether and how to trade with your own broker.

**Swing-specific:**

> Weekly setups are process screens on liquid NSE cash equities. A cash / no-new-entry week is a valid research outcome when market regime filters fail.

**Intraday-specific:**

> Intraday BUY/SELL/HOLD labels are session research bias only. Outside NSE cash hours, readings may reflect the prior session. Scalp and size risk yourself.

**MCX / Commodity-specific:**

> Directional bias uses global futures as a liquid proxy. Map front-month MCX contract, lot size, and margin yourself. Commodities are leveraged and can gap. Not MCX trading advice. We do not place orders.

**LLM-specific (when Analyze is shown):**

> Optional AI narrative is generative assistance only. It can be wrong. Prefer strategy numbers (entry/stop/target) and your own judgment over model text.

**Journal:**

> Personal research log only — not a broker ledger, performance guarantee, or advice.

**Marketing / README / PDF:** same non-guarantee stance; ban phrases like “sure shot,” “guaranteed profit,” “risk-free.”

---

## 11. Dependencies

- **Kotak Neo** consumer token for primary Swing EOD (historical).
- **NSE** bhavcopy when reachable; **Yahoo** for NIFTY series, intraday 5m, commodity futures.
- Optional third-party LLM provider (user’s key).
- Screener / fundamentals scrape or Yahoo quote fundamentals for stock modal.

---

## 12. Open questions (track, don’t block MVP)

1. Production host & auth model (self-host vs shared) — post-MVP preferred.
2. Licensed Indian OI / F&O chain vendor vs Yahoo-only OI.
3. Whether BUY/SELL rename is UI-only alias of LONG/SHORT or stored enum change.
4. SEBI communication review if product is publicly marketed in India.

---

## 13. References

- `README.md` — strategy, stack, API map  
- `QUICKSTART.md` — desk tabs  
- `backend/QA_CHECKLIST.md` — feed/data acceptance  
- `Swing_Desk_User_Guide.pdf` — end-user copy  
- `docs/ROADMAP.md` — 2-week ship plan  
