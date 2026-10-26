# Swing Desk — Beginner guide (personal research)

**Who this is for:** you, on your own computer. No trading experience or coding experience required.  
**What this is:** a research screen for NSE equities ideas and market context.  
**What this is not:** a broker, an order ticket, or a promise of profit. The app **never places orders** and **never guarantees returns**. A “signal” or research card is **not** a recommendation to buy or sell.

Version string in code: see `backend/app/main.py` (`APP_VERSION`). Guides: this file · [`QUICKSTART.md`](../QUICKSTART.md) · ops [`OPS.md`](OPS.md).

---

## 1. Start the app (first time)

1. Open a terminal and go to the project folder `bse-chief-equity-analyst`.
2. Copy the example env file (do this once):

   ```bash
   cp backend/.env.example backend/.env
   ```

3. Edit `backend/.env` with a plain text editor. Set at least:
   - `SECRET_KEY=` a long random phrase you invent (not the example default)
   - `KOTAK_CONSUMER_KEY=` your Kotak Neo Trade API consumer key (from Neo → More → Trade API), **if** you want Kotak EOD / optional live feed  
   - Leave `AUTH_ENABLED=false` and `BIND_HOST=127.0.0.1` for personal use on this machine only  
   - Leave `API_KEY=` empty for local UI (see §8). Do **not** paste secrets into the chat, screenshots, or Git.

4. Start everything:

   ```bash
   ./start.sh
   ```

5. Open a browser to **http://127.0.0.1:3000**. The API is **http://127.0.0.1:8000**.

If start fails: use `BIND_HOST=127.0.0.1` (never `0.0.0.0` with auth off). See Quickstart troubleshooting.

**First data load:** on the Swing desk, use **Force full** once (can take a long time) so end-of-day prices fill the local database. Demo / fake seeds are **forbidden** and will not invent a market for you.

---

## 2. What you see (desks)

Tabs at the top:

| Desk | What it shows | Price kind (honest labels) |
|------|----------------|----------------------------|
| **Swing** | Weekly research cards from end-of-day NSE data | **EOD** (settlement close) — not live broker LTP |
| **Intraday** | Short-horizon bias on cash names | **LIVE** only if Kotak WebSocket is connected; else Yahoo **FALLBACK**; old ticks → **STALE** and sides freeze to HOLD |
| **Index** | Nifty / Bank Nifty research bias | Same LIVE / FALLBACK / STALE rules as Intraday |
| **MCX** | Commodity *proxy* tape | Yahoo **global futures** (usually USD) — **not** exchange-listed MCX INR contracts, lots, or margins |

Also on Swing (and linked from other desks): trade journal, position size calculator, market events calendar, strategy evaluation, and a **Signal ledger**.

### Desk boards vs Signal ledger

- **Desk boards** (consultant cards): built automatically by the desk’s rules from market data. These are the research cards you read day to day.
- **Signal ledger**: an **optional notebook**. It only shows notes that someone publishes with **Publish notes**. Desk cards are **not** copied here automatically. An empty ledger is normal.

---

## 3. How to read “no signal” and banners

The banner above a board uses one of these codes:

| Code | Meaning | What you should do |
|------|---------|-------------------|
| **Qualifying** | At least one BUY/SELL research side | Read thesis, source, and freshness; still not an order |
| **No qualifying signal** | Strategy conditions not met (e.g. Swing **cash / BEAR** week when Nifty is below its SMA50) | Normal. Wait for regime / rules to allow entries — do not force buys |
| **Data blocked** | Feed stale, unavailable, or after-hours freeze | Fix data: Force full (Swing), login Kotak for LIVE, or wait for session; Yahoo failures show as unavailable/FALLBACK — never as broker LIVE |
| **Gate blocked** | History too thin or expectancy/risk gates failed for a STRONG-style badge | Card may still show HOLD; STRONG / “edge” is blocked on purpose |

**HOLD** cards can still appear when there is no BUY/SELL. That is intentional.

Freshness badges you may see: **LIVE**, **FALLBACK** (Yahoo — not broker live), **EOD**, **STALE**, **UNAVAILABLE**, **DELAYED**.

---

## 4. First-use workflow (simple)

1. Start the app (§1) and open Swing.
2. Confirm health: header tools **Test Kotak** / **Refresh** / **Force full**. Run Force full if the desk says EOD is empty or stale.
3. Read the **regime** chip (BULL / BEAR / cash). In BEAR / cash weeks, expect HOLD and “no qualifying signal” — that is the strategy working.
4. Open **Intraday** or **Index** only during NSE cash hours (~09:15–15:30 IST) if you want LIVE Kotak ticks. After close, boards freeze live sides (data blocked) even if old numbers remain visible as last observation.
5. Optional: **Publish notes** (local personal mode) to add a ledger research note with `data_mode` live/delayed/eod — not demo (demo rows are hidden).
6. Optional: **Explain with LLM** on an existing card — commentary only; needs a key in Settings (vault) or a one-shot key in the panel. The LLM **cannot** create or change BUY/SELL/HOLD.
7. Log ideas in Week Journal / Trade journal if you want a diary. Position size is a calculator only — **not** an order.

---

## 5. Optional providers (no secrets in the UI)

| Provider | Where to configure | UI |
|----------|-------------------|-----|
| Kotak EOD / WS | `KOTAK_CONSUMER_KEY` (+ session/TOTP login when you want LIVE) in `backend/.env` | Test Kotak; never paste the key into the page |
| Yahoo LTP fallback | `ALLOW_YAHOO_LTP_FALLBACK` (default on) | Shown as **FALLBACK**, never as Kotak LIVE |
| Cloud LLM (OpenAI / Anthropic) | Settings vault or one-shot key in the Explain panel | Key cleared after send; never in frontend code or Git |
| **Local LLM (Ollama / LM Studio)** | Run the server on this machine; set `LOCAL_LLM_BASE_URL` if needed | Pick a **Local ·** model in Explain / Settings — **no cloud API key** |

### Local LLM quick start (Ollama)

1. Install [Ollama](https://ollama.com) and start it (listens on `127.0.0.1:11434` by default).
2. Pull a model, e.g. `ollama pull llama3.2`.
3. In `backend/.env` (optional — these are the defaults):

   ```bash
   LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
   LOCAL_LLM_DEFAULT_MODEL=llama3.2
   ```

4. Restart the API (`./start.sh` or uvicorn).
5. On a research card, open **Explain with LLM**, choose **Local · Ollama/LM Studio · llama3.2** (or another Local entry / custom tag matching a model you pulled).
6. Click **Explain card**. No OpenAI/Anthropic key is required.

**LM Studio:** start its local server and set `LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1` (typical), then use the model id LM Studio shows.

**Safety:** the API only allows loopback hosts (`127.0.0.1` / `localhost`) for local LLM URLs — it will not call random remote hosts. Local LLM output is still **explain-only** commentary; it cannot create or change BUY/SELL/HOLD.

Backup the SQLite DB occasionally: `./scripts/backup_sqlite.sh`.

---

## 6. Market events / holiday calendar

The holiday list is an **operator-maintained snapshot** (`backend/app/data/nse_holidays.json`), not a live NSE download. If the UI says **STALE — not current**, treat dates as research-only until you:

1. Verify the latest NSE cash-market holiday circular, then  
2. Update the JSON (including a verified `as_of`).  

**Do not** bump `as_of` without that check — stale stays labeled stale on purpose.

---

## 7. Strategy evaluation

Walk-forward / stored metrics are **research evidence**. The UI states `selects_best=false` and `proven=false`. Survivorship bias is **not fully fixed** (no point-in-time universe in this desk). Options OI/PCR are **not** directional trade signals. MCX proxy is **not** evaluable as INR MCX.

---

## 8. API_KEY and local use

- Empty `API_KEY` (default): personal UI can run walk-forward without a special header.  
- If you set `API_KEY`, expensive routes (ingest, ledger mutations, strategy evaluate, GET `run_harness=true`, etc.) need header `X-API-Key`. The CRA UI does not send that header unless you add it — keep empty for local use.

Auth stays off for single-operator loopback. Do not expose the API to the public internet without auth.

---

## 9. Common problems

| Symptom | Likely cause | Next step |
|---------|--------------|-----------|
| Empty Signal ledger | No non-demo published notes; desks do not auto-fill | Use desk boards; optionally Publish notes with delayed/eod/live |
| Only HOLD / “no qualifying” on Swing | Cash / BEAR regime or filters | Read regime reason; not a crash |
| Intraday/Index “data blocked” after 15:30 IST | Session freeze | Expected; or enable Kotak LIVE during session |
| Yahoo / FALLBACK errors | Network or Yahoo blocked | Not invented LIVE; try Kotak WS or retry later |
| LLM explain 422 | No vault key / short one-shot key | Settings → vault, or paste key in panel (never commit it) |
| API won’t start on 0.0.0.0 | Safety refuse with auth off | Use `127.0.0.1` |
| Fernet / vault errors | Unstable or default `SECRET_KEY` | Set a unique stable `SECRET_KEY` before storing LLM keys |

---

## 10. Checklist

- [ ] `./start.sh` → UI on 127.0.0.1:3000  
- [ ] Unique `SECRET_KEY`, loopback bind, Kotak key if using Kotak  
- [ ] Force full at least once  
- [ ] Understand LIVE vs FALLBACK vs EOD vs STALE  
- [ ] Know desk boards ≠ ledger  
- [ ] LLM is explain-only  
- [ ] Research only — no orders, no return guarantee  

When in doubt, trust the honesty banners over any tip or hype.
