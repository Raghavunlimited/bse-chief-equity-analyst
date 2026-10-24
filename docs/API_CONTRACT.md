# Swing Desk — API Contract (v1)

**Base URL:** `http://localhost:8000` (local)  
**Content-Type:** `application/json`  
**schema_version:** `1.0`  
**App version:** `3.2.0` (see `/api/health`)

This document is the **target** public contract for multi-desk signals. Legacy routes remain until clients migrate (see §8).

**Framing:** All signal and analyze responses are research-only. No endpoint guarantees profit.

---

## Shared types

### ComplianceStamp

```json
{
  "framing": "research_only",
  "not_advice": true,
  "no_profit_guarantee": true,
  "disclaimer": "Educational research only. Not investment advice. Past patterns and backtests do not guarantee future results. You alone size risk and place orders."
}
```

| Field | Type | Required |
|-------|------|----------|
| `framing` | `"research_only"` | yes |
| `not_advice` | `boolean` | yes |
| `no_profit_guarantee` | `boolean` | yes |
| `disclaimer` | `string` | yes |

### Side

`"BUY"` | `"SELL"` | `"HOLD"`

### DeskId

`"swing"` | `"intraday"` | `"mcx"`

### Signal (core)

```json
{
  "id": "swing:2026-10-24:RELIANCE",
  "desk": "swing",
  "symbol": "RELIANCE",
  "side": "BUY",
  "score": 78.5,
  "thesis": "Breakout + volume confirm; RS vs NIFTY constructive",
  "tags": ["HH20", "VOL_CONFIRM", "RS_OK"],
  "price": 2850.0,
  "currency": "INR",
  "entry": 2852.0,
  "stop": 2760.0,
  "target": 3020.0,
  "risk_reward": 2.1,
  "as_of": "2026-10-24",
  "generated_at": "2026-10-24T11:30:00+00:00",
  "schema_version": "1.0",
  "strategy_version": "elite_momentum@3.2",
  "legacy_side": "LONG",
  "enrichment": {
    "fundamentals": null,
    "chart_summary": null
  },
  "disclaimer": "Educational research only. Not investment advice."
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | `string` | `{desk}:{as_of}:{symbol_or_id}` |
| `desk` | DeskId | |
| `symbol` | `string` | NSE ticker or commodity id (`GOLD`) |
| `side` | Side | Canonical call |
| `score` | `number` | 0–100 research score |
| `thesis` | `string` | Short consultant-style rationale |
| `tags` | `string[]` | Machine-readable factors |
| `price` | `number \| null` | Last research price |
| `currency` | `string` | e.g. `INR`, `USD` |
| `entry` / `stop` / `target` | `number \| null` | Desk-specific |
| `risk_reward` | `number \| null` | Swing primarily |
| `as_of` | `string` | Date or ISO datetime |
| `generated_at` | `string` | UTC ISO-8601 |
| `schema_version` | `string` | |
| `strategy_version` | `string` | |
| `legacy_side` | `string \| null` | Optional `LONG`/`SHORT`/`FLAT` |
| `enrichment` | `object` | Optional attach-ons |
| `disclaimer` | `string` | Per-signal echo |

### DeskBoard (list envelope)

```json
{
  "status": "ok",
  "desk": "swing",
  "as_of": "2026-10-24",
  "schema_version": "1.0",
  "strategy_version": "elite_momentum@3.2",
  "count": 3,
  "signals": [],
  "board_side": "BUY",
  "message": "Human-readable desk status",
  "poll_seconds": null,
  "meta": {},
  "compliance": {}
}
```

| Field | Type | Notes |
|-------|------|-------|
| `status` | `"ok"` \| `"empty"` \| `"degraded"` | |
| `board_side` | Side | Aggregate: cash/empty → `HOLD` |
| `poll_seconds` | `number \| null` | Live desks ≈ 15 |
| `meta` | `object` | Desk-specific (regime, session, …) |
| `compliance` | ComplianceStamp | Always present |

### Error

```json
{
  "status": "error",
  "error": {
    "code": "SIGNAL_NOT_FOUND",
    "message": "No signal with that id",
    "details": {}
  },
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice."
  }
}
```

HTTP status remains standard (`400`/`404`/`422`/`429`/`502`/`503`). Body always includes `compliance` when JSON.

---

## 1. List signals by desk

### `GET /api/signals/{desk}`

`desk` ∈ `swing` | `intraday` | `mcx`

#### Query — swing

| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `as_of` | `string` | latest EOD | `YYYY-MM-DD` |
| `capital` | `number` | `500000` | 10_000–1e9 |
| `risk_pct` | `number` | `1.0` | 0.25–5.0 |
| `max_positions` | `integer` | `3` | 1–5 |
| `reserved_cash_pct` | `number` | `20` | 0–80 |
| `entry_style` | `string` | `breakout` | `breakout` \| `pullback` |
| `target_gain_pct` | `number` | — | 0–30 optional illustrative |
| `fundamentals` | `boolean` | `true` | Attach Screener/Yahoo cache |

#### Query — intraday

| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `limit` | `integer` | `20` | 5–30 |

#### Query — mcx

None required.

#### Response `200` — swing example

```json
{
  "status": "ok",
  "desk": "swing",
  "as_of": "2026-10-24",
  "week_label": "2026-W43",
  "schema_version": "1.0",
  "strategy_version": "elite_momentum@3.2",
  "count": 2,
  "board_side": "BUY",
  "signals": [
    {
      "id": "swing:2026-10-24:RELIANCE",
      "desk": "swing",
      "symbol": "RELIANCE",
      "side": "BUY",
      "score": 81.2,
      "thesis": "Near 20d high with volume confirm; RS +4.2% vs NIFTY",
      "tags": ["BREAKOUT", "VOL_2X", "RS_OK"],
      "price": 2850.0,
      "currency": "INR",
      "entry": 2852.0,
      "stop": 2760.0,
      "target": 3020.0,
      "risk_reward": 2.05,
      "position_size": 35,
      "capital_allocated": 99700.0,
      "as_of": "2026-10-24",
      "generated_at": "2026-10-24T12:00:00+00:00",
      "schema_version": "1.0",
      "strategy_version": "elite_momentum@3.2",
      "enrichment": {
        "fundamentals": {
          "pe": 28.1,
          "source": "screener",
          "cached": true
        }
      },
      "disclaimer": "Educational research only. Not investment advice."
    }
  ],
  "message": "2 swing setups after regime and liquidity filters.",
  "poll_seconds": null,
  "meta": {
    "regime": "BULL",
    "data_status": { "status": "FRESH", "latest_date": "2026-10-24" },
    "provenance": { "data_source": "kotak" },
    "goal_plan": null
  },
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice. Past patterns and backtests do not guarantee future results. You alone size risk and place orders."
  }
}
```

Cash / no setups → `status: "empty"`, `board_side: "HOLD"`, `signals: []`, message explains regime or data gap.

#### Response `200` — intraday example

```json
{
  "status": "ok",
  "desk": "intraday",
  "as_of": "2026-10-24T05:00:00+00:00",
  "schema_version": "1.0",
  "strategy_version": "intraday_bias@3.2",
  "count": 20,
  "board_side": "BUY",
  "signals": [
    {
      "id": "intraday:2026-10-24T05:00:00Z:TCS",
      "desk": "intraday",
      "symbol": "TCS",
      "side": "BUY",
      "score": 72.0,
      "thesis": "Above VWAP proxy · ORB high break",
      "tags": ["ABOVE_VWAP", "ORB_HIGH"],
      "price": 4120.5,
      "currency": "INR",
      "stop": 4095.0,
      "target": 4165.0,
      "as_of": "2026-10-24T05:00:00+00:00",
      "generated_at": "2026-10-24T05:00:00+00:00",
      "schema_version": "1.0",
      "strategy_version": "intraday_bias@3.2",
      "legacy_side": "LONG",
      "disclaimer": "Intraday research bias only — not advice."
    }
  ],
  "message": "Live 5m Yahoo bias for liquid NSE cash. Session open — treat as active research tape.",
  "poll_seconds": 15,
  "meta": {
    "session": {
      "in_session": true,
      "pre_market": false,
      "note": "NSE cash ~09:15–15:30 IST."
    },
    "long_count": 8,
    "short_count": 4,
    "feed": "yahoo_chart_5m"
  },
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Intraday markets are noisy; no signal guarantees profit. Use hard stops and size risk 0.25–0.5% per idea."
  }
}
```

#### Response `200` — mcx example

```json
{
  "status": "ok",
  "desk": "mcx",
  "as_of": "2026-10-24T05:00:00+00:00",
  "schema_version": "1.0",
  "strategy_version": "mcx_futures_proxy@3.2",
  "count": 6,
  "board_side": "BUY",
  "signals": [
    {
      "id": "mcx:2026-10-24T05:00:00Z:GOLD",
      "desk": "mcx",
      "symbol": "GOLD",
      "side": "BUY",
      "score": 68.0,
      "thesis": "BUY · Gold @ 2650 USD/oz (+0.85%)",
      "tags": ["MOM_UP"],
      "price": 2650.0,
      "currency": "USD",
      "stop": 2628.8,
      "target": 2671.2,
      "as_of": "2026-10-24T05:00:00+00:00",
      "generated_at": "2026-10-24T05:00:00+00:00",
      "schema_version": "1.0",
      "strategy_version": "mcx_futures_proxy@3.2",
      "legacy_side": "LONG",
      "enrichment": {
        "mcx_hint": "GOLD / GOLDM",
        "yahoo_symbol": "GC=F",
        "unit": "USD/oz",
        "group": "metals"
      },
      "disclaimer": "Commodities are leveraged and can gap. Research only — not MCX advice."
    }
  ],
  "message": "Global futures tape as directional research for MCX majors. Map to front-month MCX yourself.",
  "poll_seconds": 15,
  "meta": {
    "feed": "yahoo_futures_proxy",
    "actionable_count": 3
  },
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Commodities are leveraged and can gap. Research only — not MCX advice. Confirm contract, lot size, and margin with your broker before any order."
  }
}
```

#### Errors

| HTTP | code | When |
|------|------|------|
| `404` | `UNKNOWN_DESK` | desk not in enum |
| `422` | `VALIDATION_ERROR` | bad query |
| `503` | `DATA_UNAVAILABLE` | swing with empty DB and no recoverable path |

---

## 2. Signal detail

### `GET /api/signals/{id}`

`id` is URL-encoded signal id, e.g. `swing%3A2026-10-24%3ARELIANCE`.

#### Query

| Param | Type | Default |
|-------|------|---------|
| `fundamentals` | `boolean` | `true` |
| `include_chart` | `boolean` | `false` |

#### Response `200`

```json
{
  "status": "ok",
  "signal": {
    "id": "swing:2026-10-24:RELIANCE",
    "desk": "swing",
    "symbol": "RELIANCE",
    "side": "BUY",
    "score": 81.2,
    "thesis": "Near 20d high with volume confirm; RS +4.2% vs NIFTY",
    "tags": ["BREAKOUT", "VOL_2X", "RS_OK"],
    "price": 2850.0,
    "currency": "INR",
    "entry": 2852.0,
    "stop": 2760.0,
    "target": 3020.0,
    "risk_reward": 2.05,
    "as_of": "2026-10-24",
    "generated_at": "2026-10-24T12:00:00+00:00",
    "schema_version": "1.0",
    "strategy_version": "elite_momentum@3.2",
    "enrichment": {
      "fundamentals": { "pe": 28.1, "source": "screener", "cached": true },
      "chart_summary": {
        "days": 90,
        "last_close": 2850.0,
        "sma_20": 2780.0,
        "sma_50": 2710.0
      }
    },
    "disclaimer": "Educational research only. Not investment advice."
  },
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice. Past patterns and backtests do not guarantee future results. You alone size risk and place orders."
  }
}
```

#### Errors

| HTTP | code |
|------|------|
| `404` | `SIGNAL_NOT_FOUND` |
| `400` | `INVALID_SIGNAL_ID` |

**Note:** Live desks may recompute on read if the snapshot was not persisted; id’s `as_of` is best-effort for intraday/mcx.

---

## 3. LLM analyze (BYO key)

### `POST /api/analyze`

Optional enrichment narrative. Does not change stored scores.

#### Request

```json
{
  "signal_id": "swing:2026-10-24:RELIANCE",
  "signal": null,
  "provider": "openai",
  "model": "gpt-4o-mini",
  "llm_api_key": "sk-user-provided-never-logged",
  "include": {
    "fundamentals": true,
    "chart_summary": true,
    "oi": false
  },
  "user_notes": "Optional context from the operator"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `signal_id` | `string` | one of id/signal | Preferred |
| `signal` | Signal | one of id/signal | Inline snapshot |
| `provider` | `"openai"` \| `"anthropic"` | yes | Extensible |
| `model` | `string` | no | Provider default if omitted |
| `llm_api_key` | `string` | yes | **Not persisted** |
| `include` | `object` | no | Enrichment toggles |
| `user_notes` | `string` | no | max 2000 chars |

#### Response `200`

```json
{
  "status": "ok",
  "signal_id": "swing:2026-10-24:RELIANCE",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "analysis": {
    "headline": "Constructive swing long — watch volume follow-through",
    "thesis": "…",
    "bull_case": ["…"],
    "bear_case": ["…"],
    "invalidation": "Daily close below stop region or regime flip",
    "questions": ["Has delivery % confirmed the breakout?"],
    "side_agree": true,
    "side_comment": "Aligns with BUY research call; not a guarantee"
  },
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 400
  },
  "generated_at": "2026-10-24T12:05:00+00:00",
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "LLM narrative is optional research assistance only. Not advice; model may err. Your API key was used for this request only and is not stored."
  }
}
```

#### Errors

| HTTP | code | When |
|------|------|------|
| `400` | `LLM_KEY_REQUIRED` | missing key |
| `400` | `SIGNAL_REQUIRED` | neither id nor body |
| `401` | `LLM_AUTH_FAILED` | provider rejected key |
| `404` | `SIGNAL_NOT_FOUND` | bad id |
| `429` | `LLM_RATE_LIMITED` | provider throttle |
| `502` | `LLM_UPSTREAM_ERROR` | provider 5xx / parse fail |

---

## 4. Health

### `GET /api/health`

#### Response `200`

```json
{
  "status": "ok",
  "version": "3.2.0",
  "schema_version": "1.0",
  "desks": ["swing", "intraday", "mcx"],
  "feeds": {
    "kotak": {
      "configured": true,
      "ok": true,
      "detail": "consumer key present"
    },
    "live_quotes": "yahoo_chart_5m",
    "fundamentals": "screener_yahoo_cache"
  },
  "data": {
    "freshness": "FRESH",
    "latest_eod": "2026-10-24",
    "provenance": "kotak"
  },
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice."
  }
}
```

`status` may be `"degraded"` when EOD is STALE/EMPTY but process is up (HTTP still 200 unless process unhealthy).

### `GET /`

Lightweight root identity (unchanged spirit):

```json
{
  "name": "Swing Desk",
  "version": "3.2.0",
  "desks": ["swing", "intraday", "mcx"],
  "docs": "/docs"
}
```

---

## 5. Journal

Research log only — not broker fills.

### `GET /api/journal`

| Query | Type | Default |
|-------|------|---------|
| `week` | `string` | all recent |
| `limit` | `integer` | `100` (1–500) |

#### Response `200`

```json
{
  "status": "ok",
  "week": "2026-W43",
  "count": 1,
  "entries": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "week": "2026-W43",
      "symbol": "RELIANCE",
      "invested": true,
      "capital_deployed": 100000.0,
      "pnl_rupees": 2500.0,
      "pnl_pct": 2.5,
      "notes": "Took breakout; trailed stop",
      "created_at": "2026-10-24T14:00:00+00:00",
      "disclaimer": "Personal research log only — not advice or a guarantee."
    }
  ],
  "message": "Research journal only — past P&L does not imply future results.",
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice."
  }
}
```

### `POST /api/journal`

#### Request

```json
{
  "week": "2026-W43",
  "symbol": "RELIANCE",
  "invested": true,
  "capital_deployed": 100000.0,
  "pnl_rupees": 2500.0,
  "pnl_pct": 2.5,
  "notes": "Optional notes"
}
```

`week_label` is accepted as an alias for `week`. Upserts latest row per `(week, symbol)`.

#### Response `200`

```json
{
  "status": "ok",
  "entry": { },
  "message": "Logged to research journal only — not a broker fill or return guarantee.",
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice."
  }
}
```

### `GET /api/journal/weeks`

```json
{
  "status": "ok",
  "count": 4,
  "weeks": ["2026-W43", "2026-W42"],
  "message": "Recent journal weeks — research log only.",
  "compliance": {
    "framing": "research_only",
    "not_advice": true,
    "no_profit_guarantee": true,
    "disclaimer": "Educational research only. Not investment advice."
  }
}
```

---

## 6. Related existing routes (not replaced yet)

Still part of the running app; clients may keep using them during migration:

| Method | Path | Role |
|--------|------|------|
| `GET` | `/api/weekly-picks` | Swing board (legacy) |
| `GET` | `/api/intraday/signals` | Intraday board (legacy) |
| `GET` | `/api/mcx/signals` | MCX board (legacy) |
| `POST` | `/api/ingest/latest` | EOD refresh |
| `GET` | `/api/ingest/progress` | Ingest progress |
| `GET` | `/api/market-regime` | NIFTY regime |
| `POST` | `/api/backtest` | Strategy backtest |
| `GET` | `/api/stocks` | Universe browse |
| `GET` | `/api/stock/{symbol}` | Detail + fundamentals |
| `GET` | `/api/chart/{symbol}` | OHLCV |
| `GET` | `/api/feeds/kotak` | Kotak status |

Legacy list responses use `candidates` / `signals` with `LONG`/`SHORT`/`FLAT`. Adapters map to Signal + Side in the v1 facade.

---

## 7. JSON Schema sketches (machine-readable)

### Signal

```json
{
  "$id": "https://swingdesk.local/schemas/signal.json",
  "type": "object",
  "required": [
    "id", "desk", "symbol", "side", "score", "thesis", "tags",
    "as_of", "generated_at", "schema_version", "strategy_version", "disclaimer"
  ],
  "properties": {
    "id": { "type": "string", "minLength": 3 },
    "desk": { "enum": ["swing", "intraday", "mcx"] },
    "symbol": { "type": "string", "minLength": 1 },
    "side": { "enum": ["BUY", "SELL", "HOLD"] },
    "score": { "type": "number", "minimum": 0, "maximum": 100 },
    "thesis": { "type": "string" },
    "tags": { "type": "array", "items": { "type": "string" } },
    "price": { "type": ["number", "null"] },
    "currency": { "type": "string" },
    "entry": { "type": ["number", "null"] },
    "stop": { "type": ["number", "null"] },
    "target": { "type": ["number", "null"] },
    "risk_reward": { "type": ["number", "null"] },
    "as_of": { "type": "string" },
    "generated_at": { "type": "string", "format": "date-time" },
    "schema_version": { "type": "string" },
    "strategy_version": { "type": "string" },
    "legacy_side": { "type": ["string", "null"] },
    "enrichment": { "type": "object" },
    "disclaimer": { "type": "string" }
  }
}
```

### AnalyzeRequest

```json
{
  "$id": "https://swingdesk.local/schemas/analyze-request.json",
  "type": "object",
  "required": ["provider", "llm_api_key"],
  "properties": {
    "signal_id": { "type": "string" },
    "signal": { "$ref": "signal.json" },
    "provider": { "enum": ["openai", "anthropic"] },
    "model": { "type": "string" },
    "llm_api_key": { "type": "string", "minLength": 8 },
    "include": {
      "type": "object",
      "properties": {
        "fundamentals": { "type": "boolean" },
        "chart_summary": { "type": "boolean" },
        "oi": { "type": "boolean" }
      }
    },
    "user_notes": { "type": "string", "maxLength": 2000 }
  },
  "anyOf": [
    { "required": ["signal_id"] },
    { "required": ["signal"] }
  ]
}
```

---

## 8. Migration plan (API)

1. Implement facade routers that wrap existing `generate_weekly_picks` / `build_intraday_desk` / `build_mcx_desk`.
2. Normalize `side` + attach `compliance` + stable `id`.
3. Point frontend `deskAPI` to `/api/signals/*` while keeping legacy getters as thin wrappers.
4. Add `/api/analyze` behind BYO key; ship UI only when provider smoke-tested.
5. Mark legacy paths `deprecated` in OpenAPI; remove after one minor release once CRA is fully on v1.
