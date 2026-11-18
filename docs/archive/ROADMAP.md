# Swing Desk — 2-Week Ship Plan

**Goal:** Production-ready **signals product** — Swing / Intraday / Commodity desks with professional BUY/SELL/HOLD calls, confidence surfaces (charts, OI-when-available, financials), optional BYO LLM, and compliance-safe copy.

**Anchor docs:** `docs/PRD.md` · `backend/QA_CHECKLIST.md` · `Swing_Desk_User_Guide.pdf`

**Ship date:** End of Week 2 (dogfood + CEO review)

---

## Week 1 — Signal productization & trust

### Days 1–2 · Desk language & contracts

- [ ] Normalize API/UI call labels to **BUY / SELL / HOLD** (map LONG/SHORT/FLAT; swing cash stays explicit “no new entries”).
- [ ] Ensure each signal card shows: side, symbol, score/confidence, entry (or bias), stop/invalidation, target when defined, timestamp.
- [ ] Persist desk tab + document three journeys in UI microcopy (align with PRD §4).

### Days 3–4 · Confidence surfaces

- [ ] Swing: chart + RSI path stable for EOD symbols; financials modal honest empty/error.
- [ ] Intraday/MCX: last-quote age on board; session/pre/after-hours labels verified.
- [ ] OI MVP: show field when feed returns it; else “OI unavailable” (no fake OI).
- [ ] Stale / DEMO / provenance chips audited against QA checklist.

### Days 5–7 · Optional LLM + compliance chrome

- [ ] Settings: BYO LLM API key (local/env); never log key values.
- [ ] Analyze action on signal → structured thesis + risks + invalidation; works offline without key (CTA only).
- [ ] Global + per-desk + journal + LLM disclaimers per PRD §10.2.
- [ ] Regenerate `Swing_Desk_User_Guide.pdf` with BUY/SELL language and desk tabs.
- [ ] Health/version bump if contracts change; desks array remains `swing`, `intraday`, `mcx`.

**Week 1 exit:** Dogfood on all three desks with live Kotak (or documented Yahoo fallback); no DEMO-as-live; disclaimers present.

---

## Week 2 — Harden, measure, ship

### Days 8–9 · Freshness, journal, uptime

- [ ] Expose/verify **signal freshness** in stats/UI (EOD age; intraday quote age).
- [ ] Journal save path smoke-tested; track dogfood **journal completion** (manual count OK for MVP).
- [ ] `/api/health` monitored for ship host; target ≥99% over dogfood window.
- [ ] Empty/outage states for Yahoo & Kotak (no spinner forever).

### Days 10–11 · QA & regression

- [ ] Full `backend/QA_CHECKLIST.md` pass.
- [ ] `python test_world_class.py` + `python test_api_suite.py` green.
- [ ] Manual matrix: Swing cash week · Swing pick week · Intraday session · Intraday off-hours · MCX majors · LLM with/without key.
- [ ] README / QUICKSTART aligned with shipped UX (tabs, disclaimers, non-goals).

### Days 12–14 · Ship & CEO review

- [ ] Production start path (`./start.sh` or deploy notes) documented.
- [ ] MVP must-ship checklist (below) 100% checked.
- [ ] CEO demo script: desk switch → call → chart/financials → optional Analyze → journal (Swing).
- [ ] Park v1.1 items (structured OI, alerts, custom watchlists, signal audit log) in backlog — do not slip into MVP.

**Week 2 exit:** CEO-accepted MVP; known issues listed; v1.1 backlog frozen from PRD §8.

---

## Roles (suggested)

| Role | Focus |
|------|--------|
| Eng | Labels, LLM hook, freshness fields, empty states |
| PM | Copy, acceptance sign-off, demo script, metrics definition |
| QA | Checklist, matrix, trust incidents (DEMO/stale) |
| CEO | Scope lock (no broker execution), ship / no-ship |

---

## Explicit deferrals (do not pull into 2-week window)

- Broker order placement / TOTP trading
- Cloud multi-user billing
- Licensed F&O OI vendor integration (beyond “show if present”)
- Mobile apps
- Guaranteed-return marketing

---

## MVP must-ship checklist

- [ ] **Desk switcher:** Swing / Intraday / MCX tabs work and persist
- [ ] **Swing:** regime-aware weekly BUY setups or honest cash + radar
- [ ] **Swing:** stop / target / score on picks; capital planner; week journal save
- [ ] **Intraday:** BUY/SELL/HOLD board with ~15s refresh + session labels
- [ ] **MCX:** Gold, Silver, Crude, NatGas, Copper + USDINR; contract hints
- [ ] **Charts** on symbol detail (EOD path)
- [ ] **Financials** on symbol detail or honest error
- [ ] **OI** shown when available; otherwise explicit unavailable
- [ ] **Freshness / provenance / DEMO** honesty (stale banner when needed)
- [ ] **Optional BYO LLM** Analyze; full product works without a key
- [ ] **Compliance copy** global + per-desk + journal + LLM (PRD §10.2)
- [ ] **No broker execution** APIs or order UI
- [ ] **No guarantee / sure-shot** language in UI, PDF, README
- [ ] **Health** reports desks + Kotak feed status
- [ ] **QA checklist** + automated tests green
- [ ] **User guide PDF** regenerated for ship
- [ ] **Dogfood metrics** noted: freshness SLO sample, journal saves, uptime sample
