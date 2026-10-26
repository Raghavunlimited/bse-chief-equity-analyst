# Swing Desk — CTO Production Readiness Audit

**Repo:** `bse-chief-equity-analyst`  
**Product:** Swing Desk (Swing · Intraday · MCX research signals)  
**Audit date:** 2026-10-24  
**Scope:** Production go-live readiness for a signals / research product aimed at Indian markets  
**Not legal advice:** India regulatory notes below are high-level orientation only; engage counsel / compliance before charging users or marketing tips.

---

## Executive verdict

**Not production-ready for a public or paid signals product.** Strong research desk for local/single-operator use (strategy clarity, freshness gates, feed provenance, per-desk disclaimers). Gaps in auth, CORS, deploy hardening, observability, SLA automation, and India regulatory packaging block a safe go-live.

**Phase 7 (2026-10-26) update:** Personal/local posture hardened — loopback bind by default, boot refuse for `0.0.0.0` + auth off without `ALLOW_PUBLIC_BIND`, CORS no longer defaults to `*`, SQLite backup script + schema check on `/api/health`, docs/start.sh reconciled. **Still not a production-ready public claim** (`production_ready_claim: false` on health). See `docs/OPS.md`.

### Mitigated in app v3.3.1 (partial)
- `CORS_ORIGINS` from env (default `*` for local; set explicit origins in prod)
- Optional `API_KEY` → `X-API-Key` required for ingest / journal POST / backtest / ledger / Kotak login-test / `POST /api/strategy-evaluation/evaluate` (+ `GET ?run_harness=true`). Empty `API_KEY` = open gate for personal loopback UI.
- `/api/health` = liveness; `/api/health/ready` = freshness + `ALLOW_DEMO_DATA` gate (503 when not ready)
- `ENABLE_API_DOCS=false` hides `/docs` + OpenAPI
- Kotak `env_path` no longer returned unless `LOG_LEVEL=DEBUG`
- Canonical `/api/signals/{swing,intraday,mcx}` facade (Architect contract)

Still open: India IA/RA packaging, scheduled ingest+alerts, prod metrics, SQLite tenancy/backup, hard bind `127.0.0.1` in start.sh for public hosts.

---

## 1. Current strengths

| Area | What works |
|------|------------|
| Strategy discipline | Shared `generate_weekly_picks` for live + backtest; regime gate; liquid-universe filters; explicit score / stop / target rules |
| Data honesty | DEMO badge, provenance (`demo` / Kotak / NSE / Yahoo), STALE / FRESH / RECENT freshness, stale picks blocked when `require_fresh` |
| Operator UX | Background ingest + progress poll, Kotak probe, Force full with worker cap, capital planner + journal |
| Multi-desk | Swing EOD, Intraday (Yahoo 5m), MCX majors — consistent “research only” framing in API payloads |
| Secrets hygiene (repo) | `backend/.env` gitignored; `.env.example` present; no evidence `.env` was committed |
| Test surface | `test_world_class.py`, `test_api_suite.py`, `QA_CHECKLIST.md` for feed/regression smoke |
| Config | Tunables via env (`MAX_DATA_AGE_DAYS`, ingest caps, risk, strategy thresholds) |

---

## 2. Current gaps (summary)

| Area | Gap |
|------|-----|
| Security | No auth; CORS `*`; mutating ingest/journal open; `/docs` public; `0.0.0.0` + `--reload` in `start.sh` |
| Secrets | Kotak key only in `.env` (OK locally); status leaks `env_path`; no secret manager / rotation story |
| Observability | Plain `logging.basicConfig`; health is liveness-only; no metrics, tracing, or alert hooks |
| Deploy | No Docker/compose/K8s; CRA `proxy` is dev-only; SQLite single-node; no backup/restore runbook |
| SLAs | Freshness threshold exists; no scheduled ingest, no pager on STALE, no feed SLO dashboards |
| Legal / product | Soft educational disclaimers present; missing ToS, privacy, SEBI positioning, RA vs IA clarity |
| LLM | No LLM path in current tree (old `chief_analyst` removed) — if reintroduced, keys must be isolated |

---

## 3. Security

### 3.1 LLM key handling

- **Current state:** No OpenAI / Anthropic / Gemini client in the live codebase. Signal schema (`app/signals/models.py`) is deterministic research calls, not LLM output.
- **If LLM is re-added (recommended posture):**
  - Store keys only in env / secret manager (`LLM_API_KEY`), never in git, frontend, or client bundles.
  - Server-side only; never `REACT_APP_*` for model keys.
  - Log prompts/responses without keys; redaction middleware for Authorization headers.
  - Separate budget / rate limits and kill-switch env (`LLM_ENABLED=false`).

### 3.2 `.env` / secrets

| Item | Status |
|------|--------|
| `KOTAK_CONSUMER_KEY` via `backend/.env` | Correct pattern; gitignored |
| `.env.example` | Documents Kotak + strategy knobs (no secrets) |
| Leak surface | `GET /api/feeds/kotak` and health expose `env_path` filesystem path — remove or gate in prod |
| Journal / SQLite on disk | Unencrypted local files under `backend/data/` — fine for solo laptop; not multi-tenant safe |
| Frontend | No broker secrets in CRA (good) |

**Do not commit:** `.env`, DB files, `trade_journal.json`, Kotak caches, or any pasted access tokens.

### 3.3 CORS

```python
# backend/app/main.py — current
allow_origins=["*"]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

**Issues:**

1. Wildcard origin + credentials is invalid / unsafe for browsers and invites CSRF-style abuse from any site if cookies/sessions are later added.
2. For production: set explicit `CORS_ORIGINS` (comma-separated), default empty or same-origin only; disable credentials unless using cookie auth.
3. Prefer reverse-proxy same-origin (UI + API under one host) so CORS can be locked down.

### 3.4 AuthZ / attack surface

Unauthenticated today:

- `POST /api/ingest/latest` — expensive Kotak fan-out (DoS / bill / rate-ban risk)
- `POST /api/feeds/kotak/test` — credential probe
- `POST /api/journal` — write any journal entry
- `POST /api/backtest` — CPU-heavy
- All GETs including signals, stocks, charts

**Minimum for go-live:** API key or session auth on mutating routes; optionally on all `/api/*` if the product is private. Rate-limit ingest and quote-heavy routes.

### 3.5 Other security notes

- `start.sh` binds `uvicorn --reload --host 0.0.0.0` — development only; never for internet exposure.
- OpenAPI at `/docs` and `/openapi.json` should be disabled or auth-gated in production.
- Scraping Screener.in / Yahoo cookie crumb flows (`fundamentals.py`) are brittle and may violate third-party ToS — treat as best-effort enrichment, not a contractual data feed.
- SQLite + background ingest threads: OK for single process; concurrent multi-worker uvicorn without care risks lock contention.

---

## 4. Observability

### 4.1 Logging

- Present: module loggers + `INFO` basicConfig (timestamp, name, level, message).
- Missing: structured JSON logs, request ID / correlation, access logs with status/latency, secret redaction, log shipping (CloudWatch / Datadog / Loki).

### 4.2 Health

`GET /api/health` returns `status: ok`, version, desks, Kotak configured flag, live_quotes label.

**Gaps for production:**

| Check | Needed |
|-------|--------|
| Liveness | Process up (current) |
| Readiness | DB openable; latest EOD age ≤ SLA; Kotak configured if required |
| Dependency | Kotak probe cached (not on every health scrape); Yahoo quote sample |
| Status codes | Return **503** when STALE / EMPTY / critical feed down (not always 200) |

Recommend split: `/api/health/live` vs `/api/health/ready`.

### 4.3 Metrics / alerts (absent)

Suggested minimum:

- Ingest success/fail, duration, symbols updated
- Freshness `age_days` gauge
- Kotak HTTP 429 count
- Signal endpoint latency / error rate
- Alert: STALE > N hours after market close IST; ingest stuck `running` > 45m

---

## 5. Data freshness SLAs

### 5.1 Current behaviour

| Knob / signal | Behaviour |
|---------------|-----------|
| `MAX_DATA_AGE_DAYS` (default **3**) | Calendar age vs last weekday → `FRESH` (≤1d), `RECENT` (≤ max), `STALE` (> max) |
| Weekly picks | Can return `status: stale` when freshness is STALE and `require_fresh` |
| UI | EOD chip + STALE messaging; DEMO when provenance is demo |
| Intraday / MCX | Yahoo 5m cache TTL ~12s; poll hint 15s — **not** exchange co-located feeds |
| Ingest | Manual / UI-triggered; `run_daily_ingest.py` exists but **no cron/systemd in repo** |

### 5.2 Proposed production SLAs (IST)

| Desk | Freshness target | Breach action |
|------|------------------|---------------|
| **Swing (EOD)** | Latest NSE cash EOD ≤ **1 trading day** after close (prefer same evening post-settle) | Mark STALE; hide / watermark picks; page on-call |
| **Intraday** | Quote age ≤ **60s** during session (best-effort Yahoo); show “delayed / research” badge | Degrade to FLAT + banner |
| **MCX** | Futures quote age ≤ **120s** during session | Same |
| **Ingest job** | Daily job completed by **18:45 IST** on trading days (tune to Kotak settle) | Retry ×3; alert |
| **Provenance** | Never serve DEMO silently in prod | Hard-fail boot if `ALLOW_DEMO_DATA=false` and source is demo |

Document clearly: Yahoo/Kotak are **not** official exchange real-time licensed feeds; product must not claim “live exchange data” without proper vendor contracts.

---

## 6. Legal / disclaimer requirements (India — high-level, not legal advice)

Swing Desk currently frames output as research / education. That is necessary but **not sufficient** if you:

- Charge for tips / signals / WhatsApp alerts  
- Personalize recommendations for a fee  
- Market “assured” or implied returns  
- Scale to many retail users  

**Engage Indian securities counsel.** Orientation points commonly discussed for signal-style products:

1. **SEBI Investment Advisers (IA)** — Personalized advice for consideration often implicates IA registration and conduct rules. Productized, impersonal research may still attract scrutiny depending on packaging and monetization.
2. **SEBI Research Analysts (RA)** — Publishing research reports / recommendations can fall under RA regulations (disclosures, conflicts, record-keeping). Align copy (“signals”, “calls”, “buy”) with counsel’s reading.
3. **Not a stock exchange / broker** — Do not imply execution, custody, or guaranteed fills; journal is not a broker ledger (already stated — keep it).
4. **Disclaimers & risk** — Persist on every signal payload **and** prominent UI: not investment advice; capital at risk; past performance ≠ future results; stops can gap; derivatives (MCX) carry leverage risk.
5. **Marketing** — Avoid absolute return claims, “sure shot”, or cherry-picked backtests without methodology and costs (you already model round-trip cost — disclose assumptions).
6. **Data / privacy (DPDP Act)** — If you collect emails, journals, or PII: notice, purpose limitation, retention, security. Today journal is local JSON — multi-user cloud changes the picture.
7. **Third-party data** — NSE / Kotak / Yahoo / Screener terms; commercial redistribution may need licenses.
8. **Terms of Use + Privacy Policy + Acceptable Use** — Required before public launch; include jurisdiction (India), no-liability for trading losses, and research-only scope.
9. **Operator identity** — Clear “who runs this desk” contact; if unregistered, do not hold out as SEBI-registered IA/RA.

**Product default until counsel clears monetization:** private tool for the operator; no public tip blasting; keep educational framing; watermark DEMO/STALE.

---

## 7. Go-live checklist

### A. Security & access

- [ ] Explicit `CORS_ORIGINS`; remove `*` + credentials combo  
- [ ] Auth on mutating APIs (ingest, journal write, backtest, Kotak test)  
- [ ] Rate limits on ingest + quote-heavy routes  
- [ ] Disable or protect `/docs` and `/openapi.json` in prod  
- [ ] Stop binding `0.0.0.0 --reload` for internet hosts  
- [ ] Strip `env_path` / filesystem hints from public feed status  
- [ ] Secrets only via env / secret manager; rotate Kotak token runbook  
- [ ] TLS termination (reverse proxy); HSTS  

### B. Deploy & data

- [ ] Production process manager (systemd / container) — no `start.sh` as prod  
- [ ] Frontend production build + same-origin reverse proxy (`REACT_APP_API_BASE` if split)  
- [ ] `ALLOW_DEMO_DATA=false` in prod; refuse DEMO provenance for signals  
- [ ] Scheduled `run_daily_ingest.py` (cron) + failure alerts  
- [ ] SQLite backup (or migrate Postgres) + restore drill  
- [ ] Disk quotas for `data/`, caches, journal  

### C. Observability & SLAs

- [ ] Split live/ready health; ready fails on STALE/EMPTY when markets should be fresh  
- [ ] Structured logs + request IDs  
- [ ] Metrics: freshness, ingest, 429s, API errors  
- [ ] On-call alert for SLA breach  

### D. Product / legal

- [ ] Counsel review of IA/RA positioning before paid or public signals  
- [ ] ToS, Privacy, Risk Disclosure pages linked in UI footer  
- [ ] Disclaimer on every desk + PDF/export  
- [ ] Honest “delayed / research feed” labeling for Yahoo desks  
- [ ] Version align (frontend `3.0.0` vs API `3.2.0`)  

### E. Quality gates

- [ ] `python test_world_class.py` green against staging  
- [ ] `QA_CHECKLIST.md` signed off (Kotak, provenance, STALE banner)  
- [ ] Load smoke: concurrent UI + Force full without API deadlocks  

---

## 8. Top 10 go-live blockers (ranked)

| Rank | Blocker | Why it blocks |
|------|---------|---------------|
| **1** | **No authentication on API** | Anyone who can reach the host can trigger Kotak ingest, write journal, run backtests — abuse, cost, data integrity |
| **2** | **India regulatory packaging incomplete** | Paid/public “signals” without IA/RA counsel + ToS/risk pages creates legal/compliance exposure |
| **3** | **CORS `allow_origins=["*"]` (+ credentials)** | Unsafe default for any browser-exposed API; must lock to known origins or same-origin |
| **4** | **Dev server as deploy path** | `start.sh` → `0.0.0.0` + `--reload` + CRA proxy is not a production architecture |
| **5** | **No scheduled ingest + alerting** | Freshness SLA is passive; STALE desks can ship silently after weekends/holidays without ops |
| **6** | **Health is not readiness** | Orchestrators / LBs will keep routing while DB EMPTY or EOD STALE |
| **7** | **DEMO / synthetic data can look live** | Without hard prod guard (`ALLOW_DEMO_DATA=false`), users may trade on seed prices |
| **8** | **SQLite + local JSON journal without backup/tenancy model** | Single-file durability and no multi-user isolation — fails team/cloud go-live |
| **9** | **Open `/docs` + feed status info leak** | Attack surface + `env_path` disclosure; must gate or remove |
| **10** | **No production observability (metrics/alerts/structured logs)** | Cannot detect Kotak 429 storms, stuck ingest, or SLA breach before users do |

---

## 9. Recommended near-term path

1. **Private beta (operator-only):** VPN or basic auth; fix CORS; cron ingest; ready health; `ALLOW_DEMO_DATA=false`.  
2. **Counsel pass** before any paid signal channel.  
3. **Hardening sprint:** auth, rate limits, docs off, secret scrub, backups.  
4. **Then** consider multi-user + stronger datastore.

Until items **1–5** above are closed, treat Swing Desk as a **local research terminal**, not a production signals service.
