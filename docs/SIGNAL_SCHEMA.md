# Signal record schema

Canonical fields for auditable signals (`signal_records` / API JSON):

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | Immutable row id |
| symbol | string | Instrument ticker |
| category | `intraday` \| `swing` \| `commodity` | Desk |
| direction | `buy` \| `sell` \| `none` | `none` when evidence insufficient |
| timeframe | string | e.g. `session`, `1w`, `1d` |
| status | `draft` \| `published` \| `expired` \| `revised` | |
| created_at / expires_at / published_at | ISO-8601 UTC | |
| rationale | string | Human-readable research rationale |
| evidence | object | Charts/indicators/OI/financials observations |
| provenance | object | Includes `data_mode`, `source`, `as_of`, `note` |
| risk_notes | string | Always present on publish |
| methodology_id | string | Default `baseline_v1` |
| data_mode | `live` \| `delayed` \| `stale` \| `demo` | Honest labeling |
| supersedes_id | uuid? | Prior row when revising |
| revision | int | Monotonic per lineage |

**Rules:** Never silently overwrite a published row. Never force buy/sell when evidence is thin. Never invent missing OI/price/financials.
