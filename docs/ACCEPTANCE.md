# Production acceptance checklist — Swing Desk

Use before any “ready for production” call. Automated gate: `backend/test_production_suite.py`. Manual desk walkthrough: [MANUAL_QA.md](./MANUAL_QA.md).

**Pass rule:** all Critical items checked; High items checked or explicitly waived with owner + date.

---

## 0. Preconditions

- [ ] API on `http://127.0.0.1:8000` (or staging URL documented)
- [ ] UI on expected port (proxy to API)
- [ ] `backend/.env` present; Kotak consumer key configured if claiming live EOD
- [ ] No secrets committed (`.env` gitignored)

```bash
cd backend && source venv/bin/activate && python test_production_suite.py
```

---

## 1. Critical — API smoke (automated)

| Check | Endpoint / action | Pass criteria |
|-------|-------------------|---------------|
| Health | `GET /api/health` | `200`, `status=ok`, version ≥ 3.3.0, desks include swing/intraday/mcx, feeds.kotak present, **no groww** |
| Stats | `GET /api/stats` | `200`, symbol/coverage fields present |
| Regime | `GET /api/market-regime` | `200`, regime string + allow/reason context |
| Weekly picks | `GET /api/weekly-picks` | `200`, `status` in expected set (`ok`/`cash`/`stale`/…), candidates or honest cash message |
| Journal write | `POST /api/journal` | `200`, entry echoed |
| Journal read | `GET /api/journal` | `200`, includes posted entry |
| Intraday | `GET /api/intraday/signals` | `200`, signals list (may be off-session residue) |
| MCX | `GET /api/mcx/signals` | `200`, commodity rows |
| Consultant (if shipped) | `GET /api/consultant/{swing,intraday,mcx,daily,weekly}` | `200` each; calls use BUY/SELL/HOLD |
| Analyze validation | `POST /api/analyze` without `api_key` | **`422`** (never 500) |

- [ ] `test_production_suite.py` exit code **0**

---

## 2. Critical — Product / legal

- [ ] Visible research disclaimer on every desk (swing / intraday / MCX)
- [ ] No “guaranteed returns”, tip-channel, or broker-fill language in UI copy
- [ ] LLM analyze: key stored in **browser localStorage only**; sent only as BYOK on `/api/analyze`
- [ ] Analyze response includes research disclaimer; failures do not leak API keys in logs/UI
- [ ] Provenance chip honest (KOTAK / Yahoo / demo) — never labels demo as live Kotak

---

## 3. High — Data trust & feeds

- [ ] Stats show EOD coverage + listed NSE EQ ≈ 2000+
- [ ] Stale banner when EOD older than SLA
- [ ] BEAR / cash week explains NIFTY vs SMA clearly
- [ ] `POST /api/feeds/kotak/test` returns ok + candle count when key valid
- [ ] No `/api/feeds/groww` in OpenAPI or UI

---

## 4. High — Desks & planner

- [ ] **Swing:** CapitalDesk updates capital / risk / target % and reloads picks + goal_plan
- [ ] Goal planner marks unreachable targets honestly
- [ ] Consultant swing board (or fallback picks) shows confidence + thesis
- [ ] **Intraday:** SignalBoard / tape loads; off-session note visible
- [ ] **MCX:** Gold/Silver/Crude (etc.) with leverage / map-to-lot warning
- [ ] Week journal: log symbol → appears in week list with running P&L note (research only)

---

## 5. High — LLM analyze modal

- [ ] Settings: save/clear provider key in localStorage (`swing_desk_llm_*` or equivalent)
- [ ] “Analyze with LLM” without key → clear prompt to open settings (no silent 500)
- [ ] With key: modal shows summary / bull / bear / risks / checklist or honest provider error
- [ ] Network tab: body may include `api_key`; server must not persist it

---

## 6. Medium — Stocks & performance

- [ ] Search finds RELIANCE; stock modal shows PE/ROE/mcap or honest error
- [ ] Chart loads for symbols with EOD
- [ ] Force full ingest: progress % advances; other tabs stay responsive
- [ ] CORS restricted appropriately for production host (not `*` in real deploy)

---

## 7. Sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| Eng / QA automation | | | PASS / FAIL |
| Product owner | | | PASS / FAIL |

**Build / commit / env:** _______________  
**Notes / waivers:** _______________
