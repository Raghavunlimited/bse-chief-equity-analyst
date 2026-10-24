# Manual QA — Customer MVP

Browser + API pass (2026-10-24, localhost:3000 / :8000 v4.0.0):

- [x] Sign in as `customer@swingdesk.local` / `Customer1!`
- [x] Demo banner visible; provenance badges say DEMO
- [x] Swing / Intraday / MCX desks load; signal ledgers per category
- [x] Signal ledger shows history; expired SILVER + DEMO badges
- [x] Customer has no Admin button; `/api/admin/*` → 403
- [x] Admin UI publish (`RELIANCE` / `none` / demo); API revise keeps prior `revised`
- [x] LLM vault PUT/GET/DELETE via API — key never returned (`api_key: null`)
- [ ] Settings UI key entry: browser tooling blocked typing `sk-…` strings; API vault path verified instead
- [ ] Live LLM Analyze (needs real provider key — not exercised)
- [x] Disclosure / research-only footer + DEMO framing present
- [x] `test_mvp_platform.py` — 7 OK after browser session
- [x] Mobile viewport (390×844) admin form usable

Notes:
- Fixed SettingsDrawer falsely marking vault configured when only model prefs saved.
- CRA `HOST=127.0.0.1` fails `allowedHosts`; start FE without `HOST` or with `DANGEROUSLY_DISABLE_HOST_CHECK`.
